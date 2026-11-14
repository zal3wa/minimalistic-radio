using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Fallback for formats Windows can't decode: FFmpeg turns the stream into PCM, played through winmm.
internal static class FfmpegPlayer
{
    private const int SampleRate = 48000;

    internal static void Play(string ffmpeg, string stream, CancellationToken cancel, Func<int> volume, Action started, Action<string> titleChanged)
    {
        cancel.ThrowIfCancellationRequested();
        var arguments = new System.Collections.Generic.List<string> { "-nostdin", "-hide_banner", "-nostats", "-loglevel", "debug", "-rw_timeout", "8000000" };
        if (stream.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            arguments.AddRange(new[] { "-tls_verify", "1" });
        arguments.AddRange(new[] { "-protocol_whitelist", "http,https,tcp,tls,crypto", "-i", stream,
            "-map", "0:a:0", "-vn", "-ac", "2", "-ar", SampleRate.ToString(), "-f", "s16le", "pipe:1" });

        var config = new ProcessStartInfo(ffmpeg, string.Join(" ", arguments.Select(Quote)))
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardErrorEncoding = System.Text.Encoding.UTF8
        };

        using (var decoder = Process.Start(config))
        using (cancel.Register(() => Kill(decoder)))
        {
            Task<bool> denied = ReadDiagnostics(decoder.StandardError, titleChanged);
            try
            {
                var pcm = decoder.StandardOutput.BaseStream;
                var buffer = new byte[SampleRate * 4 / 20];
                int count = ReadBuffer(pcm, buffer, cancel);
                if (count > 0)
                {
                    using (var output = new WaveOutput(buffer.Length, SampleRate))
                    {
                        bool firstBuffer = true;
                        while (count > 0)
                        {
                            output.Write(buffer, count, volume(), cancel);
                            if (firstBuffer)
                            {
                                firstBuffer = false;
                                started();
                            }
                            count = ReadBuffer(pcm, buffer, cancel);
                        }
                        output.Drain(cancel);
                    }
                }
                cancel.ThrowIfCancellationRequested();
                if (!decoder.WaitForExit(2000))
                    throw new InvalidOperationException(Lang.T("Odtwarzacz przestał odpowiadać.", "The player stopped responding."));
                if (decoder.ExitCode == 0 && count == 0) return;
                if (denied.GetAwaiter().GetResult())
                    throw new InvalidOperationException(Lang.T("Serwer stacji odmówił dostępu (403).", "The station's server refused access (403)."));
                throw new InvalidOperationException(Lang.T("Nie udało się odtworzyć stacji. Spróbuj ponownie.", "Couldn't play the station. Try again."));
            }
            finally { Kill(decoder); }
        }
    }

    // Quotes one argument the way the Microsoft C runtime parses command lines.
    private static string Quote(string value)
    {
        if (value.Length > 0 && value.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return value;
        var result = new System.Text.StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') result.Append('\\', slashes * 2 + 1);
            else result.Append('\\', slashes);
            slashes = 0;
            result.Append(c);
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }

    private static async Task<bool> ReadDiagnostics(StreamReader reader, Action<string> titleChanged)
    {
        const string marker = "Metadata update for StreamTitle:";
        bool forbidden = false;
        try
        {
            string line;
            while ((line = await reader.ReadLineAsync().ConfigureAwait(false)) != null)
            {
                int index = line.IndexOf(marker, StringComparison.Ordinal);
                if (index >= 0)
                    titleChanged(line.Substring(index + marker.Length).Trim());
                else if (line.IndexOf("403 Forbidden", StringComparison.OrdinalIgnoreCase) >= 0)
                    forbidden = true;
            }
        }
        catch (ObjectDisposedException) { }
        catch (IOException) { }
        return forbidden;
    }

    private static int ReadBuffer(Stream source, byte[] buffer, CancellationToken cancel)
    {
        int count = 0;
        while (count < buffer.Length)
        {
            cancel.ThrowIfCancellationRequested();
            int read = source.Read(buffer, count, buffer.Length - count);
            if (read == 0) break;
            count += read;
        }
        cancel.ThrowIfCancellationRequested();
        return count - count % 4;
    }

    private static void Kill(Process decoder)
    {
        try { if (!decoder.HasExited) decoder.Kill(); }
        catch (InvalidOperationException) { }
        catch (Win32Exception) { }
    }
}

internal sealed class WaveOutput : IDisposable
{
    [StructLayout(LayoutKind.Sequential, Pack = 2)]
    private struct WaveFormat
    {
        internal ushort Format, Channels;
        internal uint Rate, BytesPerSecond;
        internal ushort Alignment, Bits, Extra;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WaveHeader
    {
        internal IntPtr Data;
        internal uint Length, BytesRecorded;
        internal IntPtr User;
        internal uint Flags, Loops;
        internal IntPtr Next, Reserved;
    }

    [DllImport("winmm.dll")]
    private static extern uint waveOutOpen(out IntPtr device, uint deviceId, ref WaveFormat format,
        IntPtr callback, IntPtr instance, uint flags);
    [DllImport("winmm.dll")]
    private static extern uint waveOutPrepareHeader(IntPtr device, IntPtr header, uint size);
    [DllImport("winmm.dll")]
    private static extern uint waveOutWrite(IntPtr device, IntPtr header, uint size);
    [DllImport("winmm.dll")]
    private static extern uint waveOutUnprepareHeader(IntPtr device, IntPtr header, uint size);
    [DllImport("winmm.dll")]
    private static extern uint waveOutReset(IntPtr device);
    [DllImport("winmm.dll")]
    private static extern uint waveOutClose(IntPtr device);

    private readonly AutoResetEvent done = new AutoResetEvent(false);
    private readonly IntPtr[] headers = new IntPtr[3];
    private readonly IntPtr[] samples = new IntPtr[3];
    private readonly bool[] prepared = new bool[3];
    private readonly uint headerSize = (uint)Marshal.SizeOf(typeof(WaveHeader));
    private readonly int flagOffset = Marshal.OffsetOf(typeof(WaveHeader), "Flags").ToInt32();
    private IntPtr device;
    private int next;

    internal WaveOutput(int length, int rate)
    {
        try
        {
            var format = new WaveFormat { Format = 1, Channels = 2, Rate = (uint)rate,
                BytesPerSecond = (uint)rate * 4, Alignment = 4, Bits = 16, Extra = 0 };
            Check(waveOutOpen(out device, uint.MaxValue, ref format,
                done.SafeWaitHandle.DangerousGetHandle(), IntPtr.Zero, 0x00050000));
            for (int i = 0; i < headers.Length; i++)
            {
                samples[i] = Marshal.AllocHGlobal(length);
                headers[i] = Marshal.AllocHGlobal((int)headerSize);
            }
        }
        catch
        {
            Dispose();
            throw;
        }
    }

    internal void Write(byte[] buffer, int count, int volume, CancellationToken cancel)
    {
        IntPtr header = headers[next];
        if (prepared[next])
        {
            WaitUntilDone(header, cancel);
            Check(waveOutUnprepareHeader(device, header, headerSize));
            prepared[next] = false;
        }

        cancel.ThrowIfCancellationRequested();
        for (int i = 0; i < count; i += 2)
        {
            int sample = (short)(buffer[i] | (buffer[i + 1] << 8));
            sample = sample * volume / 100;
            buffer[i] = (byte)sample;
            buffer[i + 1] = (byte)(sample >> 8);
        }
        Marshal.Copy(buffer, 0, samples[next], count);
        Marshal.StructureToPtr(new WaveHeader { Data = samples[next], Length = (uint)count }, header, false);
        Check(waveOutPrepareHeader(device, header, headerSize));
        prepared[next] = true;
        Check(waveOutWrite(device, header, headerSize));
        next = (next + 1) % headers.Length;
    }

    internal void Drain(CancellationToken cancel)
    {
        for (int i = 0; i < headers.Length; i++)
            if (prepared[i]) WaitUntilDone(headers[i], cancel);
    }

    private void WaitUntilDone(IntPtr header, CancellationToken cancel)
    {
        while ((Marshal.ReadInt32(header, flagOffset) & 1) == 0)
        {
            cancel.ThrowIfCancellationRequested();
            done.WaitOne(25);
        }
    }

    private static void Check(uint result)
    {
        if (result != 0)
            throw new InvalidOperationException(Lang.T("Problem z urządzeniem audio Windows (", "Windows audio device problem (") + result + ").");
    }

    public void Dispose()
    {
        if (device != IntPtr.Zero)
        {
            waveOutReset(device);
            for (int i = 0; i < headers.Length; i++)
                if (prepared[i]) waveOutUnprepareHeader(device, headers[i], headerSize);
            waveOutClose(device);
            device = IntPtr.Zero;
        }
        for (int i = 0; i < headers.Length; i++)
        {
            Marshal.FreeHGlobal(headers[i]);
            Marshal.FreeHGlobal(samples[i]);
        }
        done.Dispose();
    }
}
