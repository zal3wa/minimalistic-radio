using System;
using System.IO;

// The stream is not MP3/AAC (Ogg/Opus, FLAC, HLS playlist…): Windows can't play it, so trying again won't help.
internal sealed class UnsupportedFormatException : StationRefusedException
{
    internal UnsupportedFormatException() : base(Lang.T(
        "Ta stacja nadaje w formacie, którego Windows nie odtwarza (tylko MP3 i AAC).",
        "This station uses a format Windows can't play (only MP3 and AAC).")) { }
}

internal sealed class Frame
{
    internal byte[] Data;
    internal bool IsAac;
    internal int Header;   // ADTS header length (7 or 9), 0 for MP3
    internal int Blocks;   // AAC raw data blocks in this ADTS frame
    internal int SampleRate;
    internal int Channels;
    internal int Bitrate;
    internal TimeSpan Duration;
}

// Cuts an MP3 or AAC (ADTS) byte stream into whole frames, the unit Windows' decoders take.
// Junk between frames (or a stream that starts mid-frame) is skipped by re-synchronising.
internal sealed class FrameReader
{
    internal static readonly int[] AacRates ={ 96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350 };
    private static readonly int[,] Mp3Rates = { { 11025, 12000, 8000 }, { 0, 0, 0 }, { 22050, 24000, 16000 }, { 44100, 48000, 32000 } };
    private static readonly int[] Mpeg1Layer3 = { 0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320 };
    private static readonly int[] Mpeg2Layer3 = { 0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160 };

    private readonly Stream source;
    private readonly byte[] buffer = new byte[64 * 1024];
    private int start, end;
    private bool finished;
    private bool sniffed;
    private Frame locked;

    internal FrameReader(Stream source) => this.source = source;

    // Returns the next frame, or null when the stream ends.
    internal Frame Next()
    {
        int skipped = 0;
        while (true)
        {
            if (!Fill(10)) return null;
            if (!sniffed)
            {
                sniffed = true;
                foreach (string signature in new[] { "OggS", "fLaC", "#EXT", "[playlist]", "<", "RIFF" })
                    if (StartsWith(signature)) throw new UnsupportedFormatException();
            }
            Frame frame = Parse(buffer, start, end - start);
            if (frame != null && (locked == null || Same(frame, locked)) && Fill(frame.Data.Length + 10) &&
                (locked != null || Confirmed(frame)))
            {
                Array.Copy(buffer, start, frame.Data, 0, frame.Data.Length);
                start += frame.Data.Length;
                locked = frame;
                return frame;
            }
            if (frame != null && end - start < frame.Data.Length && finished) return null;
            start++;
            // Before the first frame: no MP3/AAC sync within 64 KB means another format.
            if (++skipped > (locked == null ? 64 * 1024 : 512 * 1024))
            {
                if (locked == null) throw new UnsupportedFormatException();
                throw new InvalidDataException(Lang.T("Stacja przesyła uszkodzone dane.", "The station is sending damaged data."));
            }
        }
    }

    private bool StartsWith(string signature)
    {
        if (end - start < signature.Length) return false;
        for (int i = 0; i < signature.Length; i++)
            if (buffer[start + i] != signature[i]) return false;
        return true;
    }

    // A frame header is only trusted when the next frame right after it is valid too.
    private bool Confirmed(Frame frame)
    {
        int next = start + frame.Data.Length;
        if (end - next < 7) return finished;
        Frame following = Parse(buffer, next, end - next);
        return following != null && Same(frame, following);
    }

    private static bool Same(Frame a, Frame b) => a.IsAac == b.IsAac && a.SampleRate == b.SampleRate;

    private bool Fill(int needed)
    {
        if (needed > buffer.Length) return false;
        if (end - start >= needed) return true;
        if (start > 0)
        {
            Array.Copy(buffer, start, buffer, 0, end - start);
            end -= start;
            start = 0;
        }
        while (end < needed && !finished)
        {
            int read = source.Read(buffer, end, buffer.Length - end);
            if (read == 0) finished = true;
            end += read;
        }
        return end - start >= needed;
    }

    internal static Frame Parse(byte[] b, int i, int available)
    {
        if (available < 7 || b[i] != 0xFF) return null;
        if ((b[i + 1] & 0xF6) == 0xF0) return ParseAdts(b, i);
        if ((b[i + 1] & 0xE0) == 0xE0) return ParseMp3(b, i);
        return null;
    }

    private static Frame ParseAdts(byte[] b, int i)
    {
        int rateIndex = (b[i + 2] >> 2) & 0xF;
        if (rateIndex >= AacRates.Length) return null;
        int channels = ((b[i + 2] & 1) << 2) | (b[i + 3] >> 6);
        int length = ((b[i + 3] & 3) << 11) | (b[i + 4] << 3) | (b[i + 5] >> 5);
        int header = (b[i + 1] & 1) == 1 ? 7 : 9;
        if (length <= header || length > 8192) return null;
        int blocks = (b[i + 6] & 3) + 1;
        int samples = 1024 * blocks;
        int rate = AacRates[rateIndex];
        return new Frame
        {
            Data = new byte[length], IsAac = true, Header = header, Blocks = blocks,
            SampleRate = rate, Channels = channels == 0 ? 2 : channels,
            Bitrate = (int)((long)length * 8 * rate / samples),
            Duration = TimeSpan.FromTicks(samples * TimeSpan.TicksPerSecond / rate)
        };
    }

    private static Frame ParseMp3(byte[] b, int i)
    {
        int version = (b[i + 1] >> 3) & 3;
        int layer = (b[i + 1] >> 1) & 3;
        int bitrateIndex = b[i + 2] >> 4;
        int rateIndex = (b[i + 2] >> 2) & 3;
        if (version == 1 || layer != 1 || bitrateIndex == 0 || bitrateIndex == 15 || rateIndex == 3) return null;
        int rate = Mp3Rates[version, rateIndex];
        bool mpeg1 = version == 3;
        int bitrate = (mpeg1 ? Mpeg1Layer3 : Mpeg2Layer3)[bitrateIndex] * 1000;
        int samples = mpeg1 ? 1152 : 576;
        int length = samples / 8 * bitrate / rate + ((b[i + 2] >> 1) & 1);
        return new Frame
        {
            Data = new byte[length], IsAac = false, SampleRate = rate, Channels = (b[i + 3] >> 6) == 3 ? 1 : 2,
            Bitrate = bitrate, Duration = TimeSpan.FromTicks(samples * TimeSpan.TicksPerSecond / rate)
        };
    }
}
