using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;

// Song titles from a stream are applied at most once every 5 seconds, so a stream that sends them nonstop can't flood
// the history, the statistics, the cover search or the media controls. The first title after starting a station is
// applied at once; of several within 5 seconds, the newest is applied when they have passed, so the title shown is
// never stale. One gate per station start; Offer comes from the audio thread, the wake-up from a timer.
internal sealed class TitleGate : IDisposable
{
    internal static readonly TimeSpan Interval = TimeSpan.FromSeconds(5);
    private readonly Action<string> apply;
    private readonly TimeSpan interval;
    private readonly Func<DateTime> clock;
    private readonly Action<TimeSpan> wake;   // calls Due after the given time
    private readonly object guard = new object();
    private DateTime? applied;   // when the last title was applied
    private string waiting;
    private bool hasWaiting, disposed;
    private Timer timer;

    internal TitleGate(Action<string> apply) : this(apply, Interval, null, null) { }

    // The self-test brings a clock and a wake-up of its own (and a shorter interval).
    internal TitleGate(Action<string> apply, TimeSpan interval, Func<DateTime> clock, Action<TimeSpan> wake)
    {
        this.apply = apply;
        this.interval = interval;
        this.clock = clock ?? (() => DateTime.UtcNow);
        this.wake = wake ?? WakeLater;
    }

    internal void Offer(string title)
    {
        lock (guard)
        {
            if (disposed) return;
            DateTime now = clock();
            if (applied != null && now - applied.Value < interval)
            {
                waiting = title;
                if (!hasWaiting)
                {
                    hasWaiting = true;
                    wake(applied.Value + interval - now);
                }
                return;
            }
            applied = now;
            hasWaiting = false;
            waiting = null;
        }
        apply(title);
    }

    // The wake-up: the waiting title, once 5 seconds have passed since the last one.
    internal void Due()
    {
        string title;
        lock (guard)
        {
            if (disposed || !hasWaiting) return;
            DateTime now = clock();
            TimeSpan left = applied.Value + interval - now;
            if (left > TimeSpan.Zero)
            {
                wake(left);
                return;
            }
            title = waiting;
            applied = now;
            hasWaiting = false;
            waiting = null;
        }
        apply(title);
    }

    private void WakeLater(TimeSpan delay)
    {
        if (timer == null) timer = new Timer(_ => Due());
        timer.Change(delay, Timeout.InfiniteTimeSpan);
    }

    public void Dispose()
    {
        lock (guard)
        {
            disposed = true;
            timer?.Dispose();
            timer = null;
        }
    }

#if SELFTEST
    // Self-test (--test-menu): the first title at once, the newest of several after 5 seconds, a flood as two, nothing
    // after Dispose; with a clock and a wake-up of the test's own. Then the real timer, on a short interval.
    internal static void Verify()
    {
        void Check(bool ok, string what)
        {
            if (!ok) throw new InvalidOperationException("Tytuły co 5 s: " + what);
        }
        DateTime now = new DateTime(2026, 11, 16, 12, 0, 0, DateTimeKind.Utc);
        var applied = new List<string>();
        var wakes = new List<TimeSpan>();
        var gate = new TitleGate(applied.Add, Interval, () => now, wakes.Add);
        gate.Offer("A");
        Check(applied.SequenceEqual(new[] { "A" }) && wakes.Count == 0, "pierwszy tytuł nie od razu.");
        now = now.AddSeconds(1);
        gate.Offer("B");
        now = now.AddSeconds(1);
        gate.Offer("C");
        Check(applied.Count == 1 && wakes.SequenceEqual(new[] { TimeSpan.FromSeconds(4) }), "tytuły w ciągu 5 s nie czekają albo budzik źle ustawiony.");
        now = now.AddSeconds(2);
        gate.Due();   // 4 s after A: too early, it waits the last second
        Check(applied.Count == 1 && wakes.Count == 2 && wakes[1] == TimeSpan.FromSeconds(1), "tytuł przed upływem 5 s.");
        now = now.AddSeconds(1);
        gate.Due();
        Check(applied.SequenceEqual(new[] { "A", "C" }), "po 5 s nie najnowszy tytuł: " + string.Join(", ", applied));
        gate.Due();
        Check(applied.Count == 2, "pobudka bez czekającego tytułu coś zmieniła.");
        now = now.AddSeconds(3);
        gate.Offer("D");   // 3 s after C
        Check(applied.Count == 2 && wakes.Last() == TimeSpan.FromSeconds(2), "tytuł 3 s po poprzednim.");
        now = now.AddSeconds(2);
        gate.Due();
        Check(applied.Last() == "D" && applied.Count == 3, "tytuł D po 5 s.");
        now = now.AddSeconds(20);
        gate.Offer("E");   // after a quiet while: at once again
        Check(applied.Last() == "E" && applied.Count == 4, "tytuł po przerwie nie od razu.");
        // A flood: a title every millisecond for 5 seconds is applied twice, the last one at the end.
        int wakesBefore = wakes.Count;
        for (int n = 0; n < 5000; n++)
        {
            now = now.AddMilliseconds(1);
            gate.Offer("F" + n);
        }
        Check(applied.Count == 5 && applied.Last() == "F4999" && wakes.Count == wakesBefore + 1, "zalew tytułów: " + applied.Count + " zastosowanych.");
        gate.Due();
        Check(applied.Count == 5, "zalew tytułów: czekający starszy tytuł zastosowany po nowszym.");
        now = now.AddSeconds(1);
        gate.Offer("G");   // waiting when the station stops
        gate.Dispose();
        now = now.AddSeconds(10);
        gate.Due();
        gate.Offer("H");
        Check(applied.Count == 5, "tytuł po zakończeniu stacji.");

        // The real timer: on a 100 ms interval, the newest title arrives by itself.
        var arrived = new List<string>();
        using (var done = new ManualResetEventSlim())
        using (var real = new TitleGate(title => { lock (arrived) arrived.Add(title); if (title == "Z") done.Set(); }, TimeSpan.FromMilliseconds(100), null, null))
        {
            real.Offer("X");
            real.Offer("Y");
            real.Offer("Z");
            Check(done.Wait(TimeSpan.FromSeconds(5)), "czekający tytuł nie przyszedł sam.");
            lock (arrived) Check(arrived.SequenceEqual(new[] { "X", "Z" }), "prawdziwy budzik: " + string.Join(", ", arrived));
        }
    }
#endif
}
