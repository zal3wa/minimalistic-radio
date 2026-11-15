using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;
using static Lang;

// Listening statistics (Settings › Statistics): which station played and when, and which songs. Kept only on this
// computer, in statistics.json next to the history. Plain C# without WPF: it records sessions and songs and counts
// them for a period; the panel only shows the numbers.
internal sealed class ListeningSession
{
    internal string Station, Url;
    internal DateTime Start, End;   // UTC
    internal bool Titles;           // the station sent at least one song title during the session
}

internal sealed class PlayedSong
{
    internal string Station, Title;
    internal DateTime Time;   // UTC
}

internal enum StatisticsPeriod { All, Year, Month }

// One period's numbers, as the Statistics page shows them.
internal sealed class StatisticsSummary
{
    internal DateTime Since;   // local: the first day of the month or year, or the first session's day (All)
    internal TimeSpan Total, PerDay, Longest;
    internal int Songs, Stations;
    internal List<(string Name, string Url, TimeSpan Time)> TopStations = new List<(string, string, TimeSpan)>();
    internal double TitlesShare;   // 0–1: the part of the listening time when the station sent song titles
    internal bool EnoughTitles;    // a share of at least 20 % and some artists: Top artists can be shown
    internal List<(string Name, int Plays)> TopArtists = new List<(string, int)>();
    internal double[] Hours = new double[24];   // minutes listened in each hour of the day (local time)
    internal int BusiestHour = -1;
    internal bool Empty => Total <= TimeSpan.Zero;
}

internal sealed class Statistics
{
    // Back to the same station this soon after a dropped connection, the session goes on.
    private static readonly TimeSpan ReconnectWindow = TimeSpan.FromMinutes(2);
    // Twice the app's 5 minutes between updates of a playing session.
    private static readonly TimeSpan LongestGap = TimeSpan.FromMinutes(10);
    // Top artists need song titles for at least this part of the listening time.
    private const double EnoughTitlesShare = 0.2;
    private const int TopCount = 5;

    internal readonly List<ListeningSession> Sessions = new List<ListeningSession>();
    internal readonly List<PlayedSong> Songs = new List<PlayedSong>();
    private ListeningSession open;        // the station playing now
    private ListeningSession resumable;   // ended by a dropped connection or an error: a reconnect may continue it

    internal bool Recording => open != null;

    // Audio started (also again after a reconnect). All times are UTC.
    internal void Begin(string station, string url, DateTime now)
    {
        if (open != null && Storage.SameStream(open.Url, url))
        {
            Tick(now);
            return;
        }
        End(now, false);
        if (resumable != null && Storage.SameStream(resumable.Url, url) && now >= resumable.End && now - resumable.End <= ReconnectWindow)
        {
            open = resumable;
            open.End = now;
        }
        else
        {
            open = new ListeningSession { Station = station, Url = url, Start = now, End = now };
            Sessions.Add(open);
        }
        resumable = null;
    }

    // While the station plays: the session lasts until now (saved every few minutes, so a crash loses little). The app
    // updates it every 5 minutes; a longer gap means the computer was asleep (or its clock jumped), and nothing played
    // meanwhile, so the session isn't stretched over it.
    internal void Tick(DateTime now)
    {
        if (open != null && now > open.End && now - open.End <= LongestGap) open.End = now;
    }

    // The station stopped. canResume: not stopped on purpose (a dropped connection, an error), so a reconnect to the
    // same station within 2 minutes continues this session.
    internal void End(DateTime now, bool canResume)
    {
        if (open == null) return;
        Tick(now);
        resumable = canResume ? open : null;
        open = null;
    }

    internal void MarkTitles()
    {
        if (open != null) open.Titles = true;
    }

    // A song the history recorded (the same filters: no ads, station names or repeats).
    internal void AddSong(string station, string title, DateTime now)
    {
        Songs.Add(new PlayedSong { Station = station, Title = title, Time = now });
        MarkTitles();
    }

    // Everything goes; a station playing now starts counting again from now.
    internal void Clear(DateTime now)
    {
        Sessions.Clear();
        Songs.Clear();
        resumable = null;
        if (open == null) return;
        open.Start = open.End = now;
        open.Titles = false;
        Sessions.Add(open);
    }

    // "Artist - Title": the part before the first dash between spaces (also – and —, which some stations and the
    // radio itself use); none for a title without one.
    internal static string Artist(string title)
    {
        if (string.IsNullOrEmpty(title)) return null;
        int index = new[] { " - ", " – ", " — " }.Select(dash => title.IndexOf(dash, StringComparison.Ordinal))
            .Where(found => found >= 0).DefaultIfEmpty(-1).Min();
        string artist = index > 0 ? title.Substring(0, index).Trim() : "";
        return artist.Length > 0 ? artist : null;
    }

    // "18 min", "42 h 18 min", "386 h" (to the nearest minute).
    internal static string Duration(TimeSpan time)
    {
        long minutes = (long)Math.Round(Math.Max(0, time.TotalMinutes), MidpointRounding.AwayFromZero);
        if (minutes < 60) return L("{0} min", minutes);
        if (minutes < 100 * 60) return L("{0} h {1} min", minutes / 60, (minutes % 60).ToString("00", CultureInfo.InvariantCulture));
        return L("{0} h", minutes / 60);
    }

    // The numbers of one period, in local time (zone): the current month or year, or everything. A session over the
    // period's edge counts only its part inside (in the hours too). now is UTC.
    internal StatisticsSummary Summarize(StatisticsPeriod period, DateTime now, TimeZoneInfo zone)
    {
        var summary = new StatisticsSummary();
        DateTime today = TimeZoneInfo.ConvertTimeFromUtc(now, zone).Date;
        DateTime from = DateTime.MinValue, to = now;
        int days = 1;
        if (period != StatisticsPeriod.All)
        {
            DateTime first = period == StatisticsPeriod.Month ? new DateTime(today.Year, today.Month, 1) : new DateTime(today.Year, 1, 1);
            from = ToUtc(first, zone);
            DateTime end = ToUtc(period == StatisticsPeriod.Month ? first.AddMonths(1) : first.AddYears(1), zone);
            if (end < to) to = end;
            days = period == StatisticsPeriod.Month ? today.Day : today.DayOfYear;
            summary.Since = first;
        }

        var parts = new List<(ListeningSession Session, DateTime Start, DateTime End)>();
        foreach (ListeningSession session in Sessions)
        {
            DateTime start = session.Start > from ? session.Start : from, end = session.End < to ? session.End : to;
            if (end > start) parts.Add((session, start, end));
        }
        if (parts.Count == 0) return summary;
        if (period == StatisticsPeriod.All)
        {
            summary.Since = TimeZoneInfo.ConvertTimeFromUtc(parts.Min(part => part.Start), zone).Date;
            days = Math.Max(1, (today - summary.Since).Days + 1);
        }

        long total = 0, withTitles = 0;
        var stations = new Dictionary<string, (long Ticks, ListeningSession Latest)>(StringComparer.Ordinal);
        foreach (var (session, start, end) in parts)
        {
            long length = (end - start).Ticks;
            total += length;
            if (session.Titles) withTitles += length;
            if (end - start > summary.Longest) summary.Longest = end - start;
            string name = (session.Station ?? "").Trim();
            stations.TryGetValue(name, out var known);
            stations[name] = (known.Ticks + length, known.Latest == null || session.Start >= known.Latest.Start ? session : known.Latest);
            AddHours(summary.Hours, start, end, zone);
        }
        summary.Total = TimeSpan.FromTicks(total);
        summary.PerDay = TimeSpan.FromTicks(total / days);
        summary.Stations = stations.Count;
        summary.TopStations = stations.OrderByDescending(item => item.Value.Ticks).ThenBy(item => item.Key, StringComparer.CurrentCulture).Take(TopCount)
            .Select(item => (item.Key, item.Value.Latest.Url, TimeSpan.FromTicks(item.Value.Ticks))).ToList();
        summary.TitlesShare = (double)withTitles / total;
        for (int hour = 0; hour < 24; hour++)
            if (summary.Hours[hour] > 0 && (summary.BusiestHour < 0 || summary.Hours[hour] > summary.Hours[summary.BusiestHour])) summary.BusiestHour = hour;

        // Songs and their artists: each artist under the spelling the stations use most ("Queen", not "QUEEN").
        var artists = new Dictionary<string, Dictionary<string, int>>(StringComparer.CurrentCultureIgnoreCase);
        foreach (PlayedSong song in Songs)
        {
            if (song.Time < from || song.Time >= to) continue;
            summary.Songs++;
            string artist = Artist(song.Title);
            if (artist == null) continue;
            if (!artists.TryGetValue(artist, out Dictionary<string, int> spellings))
                artists[artist] = spellings = new Dictionary<string, int>(StringComparer.Ordinal);
            spellings.TryGetValue(artist, out int count);
            spellings[artist] = count + 1;
        }
        summary.TopArtists = artists.Values
            .Select(spellings => (Name: spellings.OrderByDescending(item => item.Value).First().Key, Plays: spellings.Values.Sum()))
            .OrderByDescending(item => item.Plays).ThenBy(item => item.Name, StringComparer.CurrentCulture).Take(TopCount).ToList();
        summary.EnoughTitles = summary.TitlesShare >= EnoughTitlesShare && summary.TopArtists.Count > 0;
        return summary;
    }

    // Midnight that doesn't exist (a clock change at midnight) is an hour later.
    private static DateTime ToUtc(DateTime local, TimeZoneInfo zone) =>
        TimeZoneInfo.ConvertTimeToUtc(zone.IsInvalidTime(local) ? local.AddHours(1) : local, zone);

    // Every time zone is a whole number of quarter hours off UTC, so the local hour can change only on a UTC quarter.
    private static void AddHours(double[] hours, DateTime start, DateTime end, TimeZoneInfo zone)
    {
        long quarter = TimeSpan.FromMinutes(15).Ticks;
        for (DateTime time = start; time < end;)
        {
            var next = new DateTime(time.Ticks - time.Ticks % quarter + quarter, DateTimeKind.Utc);
            if (next > end) next = end;
            hours[TimeZoneInfo.ConvertTimeFromUtc(time, zone).Hour] += (next - time).TotalMinutes;
            time = next;
        }
    }

    // ---- statistics.json: {"version":1,"sessions":[…],"songs":[…]}, times in UTC as 2026-11-15T19:02:00Z ----

    internal string ToJson()
    {
        var json = new StringBuilder("{\"version\":1,\"sessions\":[");
        for (int i = 0; i < Sessions.Count; i++)
        {
            ListeningSession session = Sessions[i];
            json.Append(i > 0 ? ",{" : "{").Append("\"station\":").Append(Quote(session.Station)).Append(",\"url\":").Append(Quote(session.Url))
                .Append(",\"start\":").Append(Quote(Time(session.Start))).Append(",\"end\":").Append(Quote(Time(session.End)))
                .Append(",\"titles\":").Append(session.Titles ? "true" : "false").Append('}');
        }
        json.Append("],\"songs\":[");
        for (int i = 0; i < Songs.Count; i++)
        {
            PlayedSong song = Songs[i];
            json.Append(i > 0 ? ",{" : "{").Append("\"station\":").Append(Quote(song.Station)).Append(",\"title\":").Append(Quote(song.Title))
                .Append(",\"time\":").Append(Quote(Time(song.Time))).Append('}');
        }
        return json.Append("]}").ToString();
    }

    // Replaces what is here with the file's contents; false (and nothing changed) when it isn't a statistics file.
    // Entries that make no sense are skipped.
    internal bool Load(string json)
    {
        Dictionary<string, object> root;
        try { root = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.DeserializeObject(json) as Dictionary<string, object>; }
        catch (ArgumentException) { return false; }
        catch (InvalidOperationException) { return false; }
        if (root == null) return false;
        IEnumerable<Dictionary<string, object>> Items(string key) =>
            (root.TryGetValue(key, out object list) ? list as object[] : null)?.OfType<Dictionary<string, object>>() ?? Enumerable.Empty<Dictionary<string, object>>();
        string Text(Dictionary<string, object> item, string key) => item.TryGetValue(key, out object value) ? value as string : null;
        DateTime? When(Dictionary<string, object> item, string key) =>
            DateTime.TryParse(Text(item, key), CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out DateTime time)
                ? time : (DateTime?)null;
        open = resumable = null;
        Sessions.Clear();
        Songs.Clear();
        foreach (Dictionary<string, object> item in Items("sessions"))
        {
            DateTime? start = When(item, "start"), end = When(item, "end");
            if (start == null || end == null || end < start || string.IsNullOrWhiteSpace(Text(item, "station"))) continue;
            Sessions.Add(new ListeningSession
            {
                Station = Text(item, "station"), Url = Text(item, "url"), Start = start.Value, End = end.Value,
                Titles = item.TryGetValue("titles", out object titles) && titles is bool on && on
            });
        }
        foreach (Dictionary<string, object> item in Items("songs"))
        {
            DateTime? time = When(item, "time");
            if (time != null && !string.IsNullOrWhiteSpace(Text(item, "title")))
                Songs.Add(new PlayedSong { Station = Text(item, "station"), Title = Text(item, "title"), Time = time.Value });
        }
        return true;
    }

    private static string Time(DateTime time) => time.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);

    private static string Quote(string text)
    {
        if (text == null) return "null";
        var quoted = new StringBuilder(text.Length + 2).Append('"');
        foreach (char letter in text)
        {
            if (letter == '"' || letter == '\\') quoted.Append('\\').Append(letter);
            else if (letter < ' ') quoted.Append("\\u").Append(((int)letter).ToString("x4", CultureInfo.InvariantCulture));
            else quoted.Append(letter);
        }
        return quoted.Append('"').ToString();
    }

#if SELFTEST
    // Self-test (--test-menu): periods and their edges, sessions over midnight, a month, a year and a clock change,
    // reconnects, the average per day, the time format, the top lists, the song titles' share and the hours.
    internal static void Verify()
    {
        // Warsaw's time zone, whatever the computer's: its clocks go back on 25 October 2026.
        TimeZoneInfo zone = TimeZoneInfo.FindSystemTimeZoneById("Central European Standard Time");
        DateTime At(int year, int month, int day, int hour, int minute = 0) =>
            TimeZoneInfo.ConvertTimeToUtc(new DateTime(year, month, day, hour, minute, 0), zone);
        DateTime now = At(2026, 11, 15, 22);
        void Check(bool ok, string what)
        {
            if (!ok) throw new InvalidOperationException("Statystyki: " + what);
        }
        Statistics Played(params (string station, DateTime start, DateTime end, bool titles)[] sessions)
        {
            var played = new Statistics();
            foreach (var (station, start, end, titles) in sessions)
                played.Sessions.Add(new ListeningSession
                {
                    Station = station, Url = "https://" + station.Replace(' ', '-') + ".example/live", Start = start, End = end, Titles = titles
                });
            return played;
        }

        // The time format: under an hour, under 100 hours, from 100 hours.
        string language = Setting;
        try
        {
            Setting = "en";
            foreach (var (minutes, expected) in new (double, string)[] { (0, "0 min"), (18, "18 min"), (59.4, "59 min"), (59.6, "1 h 00 min"),
                (42 * 60 + 18, "42 h 18 min"), (11 * 60 + 5, "11 h 05 min"), (99 * 60 + 59.4, "99 h 59 min"), (99 * 60 + 59.6, "100 h"), (386 * 60 + 40, "386 h") })
                Check(Duration(TimeSpan.FromMinutes(minutes)) == expected, $"format czasu {minutes} min → {Duration(TimeSpan.FromMinutes(minutes))}, a ma być {expected}.");
        }
        finally { Setting = language; }

        // Periods: a session over the turn of October and November counts half in November, all of it in 2026.
        Statistics edge = Played(("Edge", At(2026, 10, 31, 23), At(2026, 11, 1, 1), false));
        Check(edge.Summarize(StatisticsPeriod.Month, now, zone).Total == TimeSpan.FromHours(1), "sesja na przełomie miesięcy w listopadzie.");
        Check(edge.Summarize(StatisticsPeriod.Year, now, zone).Total == TimeSpan.FromHours(2), "sesja na przełomie miesięcy w roku.");
        // …over New Year: half of it in 2026, all of it in All.
        Statistics newYear = Played(("Edge", At(2025, 12, 31, 23, 30), At(2026, 1, 1, 0, 30), false));
        Check(newYear.Summarize(StatisticsPeriod.Year, now, zone).Total == TimeSpan.FromMinutes(30), "sesja w sylwestra w roku.");
        Check(newYear.Summarize(StatisticsPeriod.Month, now, zone).Empty, "sesja w sylwestra w listopadzie.");
        StatisticsSummary all = newYear.Summarize(StatisticsPeriod.All, now, zone);
        Check(all.Total == TimeSpan.FromHours(1) && all.Since == new DateTime(2025, 12, 31), "sesja w sylwestra we wszystkim.");
        // …from before the period's start up to after now: only the part inside counts.
        Check(Played(("Long", At(2026, 10, 20, 12), At(2026, 11, 2, 0), false)).Summarize(StatisticsPeriod.Month, now, zone).Total == TimeSpan.FromDays(1),
            "długa sesja od października.");

        // The hours: over midnight, both sides; at the clock change (02:00–03:00 twice), each hour as it was on the clock.
        StatisticsSummary night = Played(("Night", At(2026, 11, 14, 23, 30), At(2026, 11, 15, 0, 45), false)).Summarize(StatisticsPeriod.Month, now, zone);
        Check(night.Hours[23] == 30 && night.Hours[0] == 45 && night.Hours.Sum() == 75 && night.BusiestHour == 0, "godziny sesji o północy.");
        DateTime before = new DateTime(2026, 10, 24, 23, 30, 0, DateTimeKind.Utc);   // 01:30 summer time, three hours to 03:30 winter time
        StatisticsSummary change = Played(("Clock", before, before.AddHours(3), false)).Summarize(StatisticsPeriod.Year, now, zone);
        Check(change.Total == TimeSpan.FromHours(3) && change.Hours[1] == 30 && change.Hours[2] == 120 && change.Hours[3] == 30,
            "godziny przy zmianie czasu: " + string.Join(", ", change.Hours.Select((minutes, hour) => hour + "=" + minutes).Where(text => !text.EndsWith("=0"))));

        // Per day: the days so far of the month (15) and of the year (319); in All, the days since the first session (at least 1).
        Statistics month = Played(("A", At(2026, 11, 10, 8), At(2026, 11, 10, 23), false), ("A", At(2026, 11, 12, 8), At(2026, 11, 12, 23), false));
        Check(month.Summarize(StatisticsPeriod.Month, now, zone).PerDay == TimeSpan.FromHours(2), "średnia dzienna w miesiącu.");
        Check(month.Summarize(StatisticsPeriod.Year, now, zone).PerDay == TimeSpan.FromTicks(TimeSpan.FromHours(30).Ticks / 319), "średnia dzienna w roku.");
        Check(month.Summarize(StatisticsPeriod.All, now, zone).PerDay == TimeSpan.FromHours(5), "średnia dzienna od pierwszej sesji (6 dni).");
        Check(Played(("A", At(2026, 11, 15, 20), At(2026, 11, 15, 21), false)).Summarize(StatisticsPeriod.All, now, zone).PerDay == TimeSpan.FromHours(1),
            "średnia dzienna pierwszego dnia.");

        // Reconnects: back to the same station within 2 minutes after a dropped connection, the session goes on.
        var recorded = new Statistics();
        DateTime t = At(2026, 11, 15, 18);
        recorded.Begin("Radio A", "https://a.example/live", t);
        recorded.Begin("Radio A", "https://a.example/live", t.AddMinutes(1));      // audio starting again inside one session
        Check(recorded.Recording && recorded.Sessions.Count == 1, "drugi start tej samej sesji.");
        recorded.End(t.AddMinutes(10), true);                                       // the connection dropped
        Check(!recorded.Recording, "sesja po zerwaniu połączenia.");
        recorded.Begin("Radio A", "http://A.example/live/", t.AddMinutes(12));     // back within 2 minutes (the same stream)
        recorded.Tick(t.AddMinutes(20));
        Check(recorded.Sessions.Count == 1 && recorded.Sessions[0].End == t.AddMinutes(20), "powrót w ciągu 2 minut to ta sama sesja.");
        recorded.End(t.AddMinutes(20), true);
        recorded.Begin("Radio A", "https://a.example/live", t.AddMinutes(23));     // 3 minutes later: a new one
        Check(recorded.Sessions.Count == 2, "powrót po 3 minutach to nowa sesja.");
        recorded.End(t.AddMinutes(30), false);                                      // Stop
        recorded.Begin("Radio A", "https://a.example/live", t.AddMinutes(31));
        Check(recorded.Sessions.Count == 3, "po zatrzymaniu nowa sesja.");
        recorded.End(t.AddMinutes(32), true);
        recorded.Begin("Radio B", "https://b.example/live", t.AddMinutes(32));     // another station: a new one…
        recorded.End(t.AddMinutes(33), true);
        recorded.Begin("Radio A", "https://a.example/live", t.AddMinutes(34));     // …and back to the first one: also new
        Check(recorded.Sessions.Count == 5, "zmiana stacji to nowa sesja.");
        recorded.AddSong("Radio A", "Queen - A Kind Of Magic", t.AddMinutes(35));
        Check(recorded.Sessions[4].Titles && !recorded.Sessions[3].Titles && recorded.Songs.Count == 1, "tytuły w sesji.");
        recorded.Clear(t.AddMinutes(40));   // the station keeps playing: its session starts again from now
        Check(recorded.Songs.Count == 0 && recorded.Sessions.Count == 1 && recorded.Recording && recorded.Sessions[0].Start == t.AddMinutes(40) &&
            !recorded.Sessions[0].Titles, "czyszczenie w trakcie słuchania.");
        // Asleep (no update for hours), the computer played nothing: waking up doesn't stretch the session over the night.
        recorded.Tick(t.AddMinutes(45));
        recorded.End(t.AddHours(9), true);
        recorded.Begin("Radio A", "https://a.example/live", t.AddHours(9));
        Check(recorded.Sessions.Count == 2 && recorded.Sessions[0].End == t.AddMinutes(45), "sesja po uśpieniu komputera.");

        // Top lists, the songs, the share of song titles and the 20 % threshold.
        Statistics top = Played(("Antyradio Hard", At(2026, 11, 2, 20), At(2026, 11, 2, 22), true), ("Radio 357", At(2026, 11, 3, 20), At(2026, 11, 3, 23), false),
            ("RMF Classic", At(2026, 11, 4, 20), At(2026, 11, 4, 20, 30), false), ("Jazz", At(2026, 11, 5, 9), At(2026, 11, 5, 10), false),
            ("Rock", At(2026, 11, 6, 9), At(2026, 11, 6, 9, 20), false), ("Pop", At(2026, 11, 7, 9), At(2026, 11, 7, 9, 10), false),
            ("Radio 357", At(2026, 10, 3, 20), At(2026, 10, 3, 23), false));   // October: not in this month
        foreach (var (title, day) in new[] { ("Queen - A Kind Of Magic", 2), ("QUEEN - Bohemian Rhapsody", 2), ("Leonard Cohen - Everybody Knows", 2),
            ("Queen – Radio Ga Ga", 3), ("Dżingiel", 3), ("Editors - Shadow", 4), ("Daughtry - What About Now", 4), ("Metallica - One", 5), ("Muse - Uprising", 5),
            ("Leonard Cohen - Hallelujah", 6), ("Queen - Old", 10 - 40) })
            top.Songs.Add(new PlayedSong { Station = "Antyradio Hard", Title = title, Time = day > 0 ? At(2026, 11, day, 21) : At(2026, 10, 1, 21) });
        StatisticsSummary summary = top.Summarize(StatisticsPeriod.Month, now, zone);
        Check(string.Join("|", summary.TopStations.Select(item => item.Name + " " + item.Time.TotalMinutes)) ==
            "Radio 357 180|Antyradio Hard 120|Jazz 60|RMF Classic 30|Rock 20", "najczęściej słuchane stacje: " +
            string.Join("|", summary.TopStations.Select(item => item.Name + " " + item.Time.TotalMinutes)));
        Check(summary.TopStations[0].Url == "https://Radio-357.example/live", "adres stacji w zestawieniu.");
        Check(summary.Stations == 6 && summary.Songs == 10 && summary.Longest == TimeSpan.FromHours(3), "liczba stacji, utworów i najdłuższa sesja.");
        Check(string.Join("|", summary.TopArtists.Select(item => item.Name + " " + item.Plays)) == "Queen 3|Leonard Cohen 2|Daughtry 1|Editors 1|Metallica 1",
            "najczęściej grani wykonawcy: " + string.Join("|", summary.TopArtists.Select(item => item.Name + " " + item.Plays)));
        Check(Math.Abs(summary.TitlesShare - 120.0 / 420) < 1e-9 && summary.EnoughTitles, "udział tytułów 29%.");
        Check(summary.Hours[20] == 150 && summary.Hours[21] == 120 && summary.Hours[22] == 60 && summary.Hours[9] == 90 && summary.BusiestHour == 20,
            "godziny słuchania.");
        top.Sessions[0].End = At(2026, 11, 2, 20, 40);   // 40 of 340 minutes: 12 %
        StatisticsSummary few = top.Summarize(StatisticsPeriod.Month, now, zone);
        Check(few.TitlesShare < 0.2 && !few.EnoughTitles && few.TopArtists.Count == 5, "udział tytułów poniżej 20%.");
        Check(Artist("Leonard Cohen - Everybody Knows") == "Leonard Cohen" && Artist("A - B - C") == "A" && Artist("Dżingiel") == null &&
            Artist("ARIANA GRANDE / MAC MILLER – The Way") == "ARIANA GRANDE / MAC MILLER" && Artist(" - Untitled") == null, "wykonawca z tytułu.");
        Check(new Statistics().Summarize(StatisticsPeriod.All, now, zone).Empty && new Statistics().Summarize(StatisticsPeriod.All, now, zone).BusiestHour == -1,
            "puste statystyki.");

        // The file: the shape of the spec, and the same data after reading it back.
        var saved = new Statistics();
        saved.Sessions.Add(new ListeningSession { Station = "Antyradio \"Hard\"", Url = "https://a.example/live", Start = new DateTime(2026, 11, 15, 19, 2, 0, DateTimeKind.Utc),
            End = new DateTime(2026, 11, 15, 20, 41, 30, DateTimeKind.Utc), Titles = true });
        saved.Songs.Add(new PlayedSong { Station = "Antyradio \"Hard\"", Title = "Leonard Cohen - Everybody Knows \\ Żółć", Time = new DateTime(2026, 11, 15, 19, 5, 12, DateTimeKind.Utc) });
        string json = saved.ToJson();
        Check(json.StartsWith("{\"version\":1,\"sessions\":[{\"station\":\"Antyradio \\\"Hard\\\"\",\"url\":\"https://a.example/live\",\"start\":\"2026-11-15T19:02:00Z\",\"end\":\"2026-11-15T20:41:30Z\",\"titles\":true}]"),
            "kształt pliku: " + json);
        var loaded = new Statistics();
        Check(loaded.Load(json) && loaded.Sessions.Count == 1 && loaded.Songs.Count == 1 && loaded.Sessions[0].Station == "Antyradio \"Hard\"" &&
            loaded.Sessions[0].Start == saved.Sessions[0].Start && loaded.Sessions[0].Start.Kind == DateTimeKind.Utc && loaded.Sessions[0].End == saved.Sessions[0].End &&
            loaded.Sessions[0].Titles && loaded.Songs[0].Title == saved.Songs[0].Title && loaded.Songs[0].Time == saved.Songs[0].Time, "odczyt zapisanego pliku.");
        Check(!new Statistics().Load("not json") && !new Statistics().Load("[1]"), "odczyt uszkodzonego pliku.");
    }
#endif
}
