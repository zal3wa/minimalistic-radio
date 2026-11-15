using System;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Threading;
using System.Threading.Tasks;
using Windows.Media.Core;
using Windows.Media.MediaProperties;
using Windows.Media.Playback;
using Windows.Storage.Streams;
using static Lang;

// Plays an MP3/AAC radio stream with the decoders built into Windows:
// frames from FrameReader are handed one by one to a MediaStreamSource.
internal static class StreamPlayer
{
    private static string ConnectionLost => L("The connection to the station was lost.");

    // Blocks until the stream ends (returns), fails (throws) or is cancelled (throws OperationCanceledException).
    // Throws UnsupportedFormatException, before any sound, for streams Windows cannot decode.
    internal static void Play(string url, CancellationToken cancel, Func<int> volume, Action started, Action<string> titleChanged)
    {
        if (new Uri(url).AbsolutePath.EndsWith(".m3u8", StringComparison.OrdinalIgnoreCase))
            throw new UnsupportedFormatException();
        using (RadioStream stream = RadioStream.Open(url, titleChanged, cancel))
        using (cancel.Register(stream.Dispose))
        {
            var frames = new FrameReader(stream);
            Frame first;
            try { first = frames.Next(); }
            catch (Exception error) when (cancel.IsCancellationRequested && !(error is UnsupportedFormatException))
            { throw new OperationCanceledException(cancel); }
            catch (Exception error) when (error is System.IO.IOException || error is System.IO.InvalidDataException)
            { throw new InvalidOperationException(ConnectionLost, error); }
            if (first == null) throw new InvalidOperationException(L("The station isn't sending any sound."));

            var done = new TaskCompletionSource<Exception>();
            MediaStreamSource source = CreateSource(frames, first, cancel, done);
            using (var player = new MediaPlayer())
            {
                player.CommandManager.IsEnabled = false;
                player.AudioCategory = MediaPlayerAudioCategory.Media;
                int level = volume();
                player.Volume = level / 100.0;
                bool playing = false;
                // A decoder failure before the first sound means Windows can't play this format.
                player.MediaFailed += (_, e) => done.TrySetResult(playing
                    ? new InvalidOperationException(L("Couldn't play the station. Try again."))
                    : new UnsupportedFormatException());
                player.PlaybackSession.PlaybackStateChanged += (session, _) =>
                {
                    if (playing || session.PlaybackState != MediaPlaybackState.Playing) return;
                    playing = true;
                    started();
                };
                player.Source = MediaSource.CreateFromMediaStreamSource(source);
                player.Play();

                while (!done.Task.Wait(100))
                {
                    int current = volume();
                    if (current != level) player.Volume = (level = current) / 100.0;
                }
                player.Pause();
                cancel.ThrowIfCancellationRequested();
                if (done.Task.Result != null) throw done.Task.Result;
            }
        }
    }

    // Separate from Play so the decoding path can be tested without a speaker.
    internal static MediaStreamSource CreateSource(FrameReader frames, Frame first, CancellationToken cancel,
        TaskCompletionSource<Exception> done)
    {
        // ADTS never says whether a stream is HE-AAC (AAC+), and Windows' decoder then plays only the
        // AAC core: mono and muffled. Low-rate AAC is in practice always HE-AAC, so for it the frames
        // go in raw with an explicit HE-AAC configuration instead.
        byte[] heAac = first.IsAac ? HeAacConfig(first) : null;
        AudioEncodingProperties format;
        if (heAac != null)
        {
            format = AudioEncodingProperties.CreateAac((uint)first.SampleRate * 2, 2, (uint)first.Bitrate);
            format.SetFormatUserData(heAac);
        }
        else if (first.IsAac)
            format = AudioEncodingProperties.CreateAacAdts((uint)first.SampleRate, (uint)first.Channels, (uint)first.Bitrate);
        else
            format = AudioEncodingProperties.CreateMp3((uint)first.SampleRate, (uint)first.Channels, (uint)first.Bitrate);
        var source = new MediaStreamSource(new AudioStreamDescriptor(format))
        {
            CanSeek = false,
            BufferTime = TimeSpan.FromMilliseconds(750)
        };
        Frame pending = first;
        TimeSpan time = TimeSpan.Zero;
        source.Starting += (_, e) => e.Request.SetActualStartPosition(TimeSpan.Zero);
        source.SampleRequested += (_, e) =>
        {
            MediaStreamSourceSampleRequest request = e.Request;
            MediaStreamSourceSampleRequestDeferral deferral = request.GetDeferral();
            Task.Run(() =>
            {
                try
                {
                    Frame frame = pending ?? frames.Next();
                    pending = null;
                    if (frame == null)
                    {
                        done.TrySetResult(null);
                        return;
                    }
                    IBuffer data = heAac != null
                        ? frame.Data.AsBuffer(frame.Header, frame.Data.Length - frame.Header)
                        : frame.Data.AsBuffer();
                    MediaStreamSample sample = MediaStreamSample.CreateFromBuffer(data, time);
                    sample.Duration = frame.Duration;
                    time += frame.Duration;
                    request.Sample = sample;
                }
                catch (Exception error)
                {
                    done.TrySetResult(cancel.IsCancellationRequested ? null
                        : error as InvalidOperationException ?? new InvalidOperationException(ConnectionLost, error));
                }
                finally { deferral.Complete(); }
            });
        };
        return source;
    }

    // MF_MT_USER_DATA for raw AAC: the HEAACWAVEINFO fields after WAVEFORMATEX (12 bytes,
    // payload type 0 = raw), then an AudioSpecificConfig with explicit SBR (and PS for a mono core).
    private static byte[] HeAacConfig(Frame first)
    {
        int core = Array.IndexOf(FrameReader.AacRates, first.SampleRate);
        int extended = Array.IndexOf(FrameReader.AacRates, first.SampleRate * 2);
        if (first.SampleRate > 24000 || first.Blocks != 1 || first.Channels > 2 || core < 0 || extended < 0)
            return null;
        uint bits = 0;
        int used = 0;
        void Put(int value, int width) { bits = (bits << width) | (uint)value; used += width; }
        Put(first.Channels == 1 ? 29 : 5, 5);  // audio object type: PS (HE-AAC v2) or SBR (HE-AAC)
        Put(core, 4);
        Put(first.Channels, 4);
        Put(extended, 4);
        Put(2, 5);                              // underlying AAC LC
        Put(0, 3);                              // GASpecificConfig: 1024 samples, no core coder, no extension
        bits <<= 32 - used;
        var data = new byte[16];
        data[2] = 0xFE;                         // wAudioProfileLevelIndication: unspecified
        for (int i = 0; i < 4; i++) data[12 + i] = (byte)(bits >> (24 - 8 * i));
        return data;
    }
}
