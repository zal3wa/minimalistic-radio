using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

// Finds ffmpeg.exe, and on a computer without it downloads a pinned build once into
// %LOCALAPPDATA%\Minimalistic Radio\ffmpeg. Only needed for formats Windows can't decode.
internal static class FFmpeg
{
    private const string Url = "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip";
    private const string Sha256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba";
    private static readonly TimeSpan StallTimeout = TimeSpan.FromSeconds(30);

    internal static readonly string Folder = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Minimalistic Radio", "ffmpeg");

    private static readonly object gate = new object();
    private static Task<string> download;
    private static Action<int> progress;

    // Returns the path to ffmpeg.exe. All callers share one download, so switching stations
    // while it runs does not start it again; a failed download is retried by the next caller.
    internal static Task<string> EnsureAsync(Action<int> onProgress, CancellationToken cancel)
    {
        string found = Locate();
        if (found != null) return Task.FromResult(found);
        Volatile.Write(ref progress, onProgress);
        Task<string> shared;
        lock (gate)
        {
            if (download == null || download.IsFaulted || download.IsCanceled)
                download = Task.Run(() => DownloadAsync(Folder, percent => Volatile.Read(ref progress)?.Invoke(percent)));
            shared = download;
        }
        return WithCancellation(shared, cancel);
    }

    private static async Task<string> WithCancellation(Task<string> task, CancellationToken cancel)
    {
        var cancelled = new TaskCompletionSource<bool>();
        using (cancel.Register(() => cancelled.TrySetResult(true)))
            if (await Task.WhenAny(task, cancelled.Task).ConfigureAwait(false) != task)
                throw new OperationCanceledException(cancel);
        return await task.ConfigureAwait(false);
    }

    // ffmpeg.exe next to the radio, downloaded by it, in C:\ffmpeg\bin or on PATH; null when there is none.
    internal static string Locate()
    {
        var candidates = new[]
        {
            Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "ffmpeg.exe"),
            Path.Combine(Folder, "ffmpeg.exe"),
            @"C:\ffmpeg\bin\ffmpeg.exe"
        }.Concat((Environment.GetEnvironmentVariable("PATH") ?? "")
            .Split(new[] { Path.PathSeparator }, StringSplitOptions.RemoveEmptyEntries)
            .Select(dir => dir.Trim().Trim('"'))
            .Where(dir => dir.Length > 0 && dir.IndexOfAny(Path.GetInvalidPathChars()) < 0)
            .Select(dir => Path.Combine(dir, "ffmpeg.exe")));
        return candidates.FirstOrDefault(File.Exists);
    }

    internal static async Task<string> DownloadAsync(string folder, Action<int> onProgress)
    {
        Directory.CreateDirectory(folder);
        foreach (string leftover in Directory.EnumerateFiles(folder, "*.part"))
        {
            try { File.Delete(leftover); }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { }
        }

        string archive = Path.Combine(folder, Guid.NewGuid().ToString("N") + ".zip.part");
        string extracted = Path.Combine(folder, Guid.NewGuid().ToString("N") + ".exe.part");
        string target = Path.Combine(folder, "ffmpeg.exe");
        try
        {
            await Fetch(archive, onProgress).ConfigureAwait(false);
            using (ZipArchive zip = ZipFile.OpenRead(archive))
            {
                ZipArchiveEntry entry = zip.Entries.FirstOrDefault(e =>
                        e.FullName.EndsWith("/bin/ffmpeg.exe", StringComparison.OrdinalIgnoreCase))
                    ?? throw new InvalidDataException("Archiwum nie zawiera ffmpeg.exe.");
                entry.ExtractToFile(extracted, true);
            }
            if (File.Exists(target)) File.Delete(target);
            File.Move(extracted, target);
            return target;
        }
        catch (Exception error) when (error is HttpRequestException || error is IOException || error is InvalidDataException
            || error is OperationCanceledException || error is UnauthorizedAccessException)
        {
            Debug.WriteLine(error);
            throw new InvalidOperationException(Lang.T("Nie udało się pobrać FFmpeg. Sprawdź internet i spróbuj ponownie.",
                "Couldn't download FFmpeg. Check your internet connection and try again."), error);
        }
        finally
        {
            foreach (string part in new[] { archive, extracted })
            {
                try { File.Delete(part); }
                catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { }
            }
        }
    }

    private static async Task Fetch(string path, Action<int> onProgress)
    {
        using (var client = new HttpClient { Timeout = Timeout.InfiniteTimeSpan })
        using (var stalled = new CancellationTokenSource(StallTimeout))
        {
            // Cancels only when no data arrives for StallTimeout, so slow links still finish.
            client.DefaultRequestHeaders.UserAgent.ParseAdd("MinimalisticRadio");
            using (HttpResponseMessage response = await client.GetAsync(Url,
                HttpCompletionOption.ResponseHeadersRead, stalled.Token).ConfigureAwait(false))
            {
                response.EnsureSuccessStatusCode();
                long total = response.Content.Headers.ContentLength ?? 0;
                using (Stream source = await response.Content.ReadAsStreamAsync().ConfigureAwait(false))
                using (var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1 << 16, true))
                using (SHA256 hash = SHA256.Create())
                {
                    var buffer = new byte[1 << 16];
                    long received = 0;
                    int reported = -1;
                    while (true)
                    {
                        stalled.CancelAfter(StallTimeout);
                        int read = await source.ReadAsync(buffer, 0, buffer.Length, stalled.Token).ConfigureAwait(false);
                        if (read == 0) break;
                        hash.TransformBlock(buffer, 0, read, null, 0);
                        await file.WriteAsync(buffer, 0, read, stalled.Token).ConfigureAwait(false);
                        received += read;
                        int percent = total > 0 ? (int)Math.Min(99, received * 100 / total) : 0;
                        if (percent != reported)
                        {
                            reported = percent;
                            onProgress?.Invoke(percent);
                        }
                    }
                    hash.TransformFinalBlock(new byte[0], 0, 0);
                    string actual = BitConverter.ToString(hash.Hash).Replace("-", "");
                    if (!string.Equals(actual, Sha256, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Pobrany FFmpeg ma niepoprawną sumę kontrolną.");
                }
            }
        }
        onProgress?.Invoke(100);
    }
}
