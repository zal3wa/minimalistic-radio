using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

internal sealed class Release
{
    internal Version Version;
    internal string Tag, Page, Notes, Download, Sha256;
}

// Updates from the GitHub releases of the project, the way ShareX does it: the radio looks for a newer
// release at most once a day, tells about each version once, and installs it only when asked.
internal static class Updater
{
    internal const string Repository = "zal3wa/minimalistic-radio";
    internal static string Page => "https://github.com/" + Repository;

    internal static Version Current
    {
        get
        {
            Version version = typeof(Updater).Assembly.GetName().Version;
            return new Version(version.Major, version.Minor, Math.Max(0, version.Build));
        }
    }

    internal static Version ParseVersion(string tag) =>
        Version.TryParse((tag ?? "").Trim().TrimStart('v', 'V'), out Version version)
            ? new Version(version.Major, version.Minor, Math.Max(0, version.Build)) : null;

    private static string Exe => System.Reflection.Assembly.GetEntryAssembly().Location;

    // The newest published release, or null when there is none yet.
    internal static async Task<Release> Latest(HttpClient client)
    {
        using (var request = new HttpRequestMessage(HttpMethod.Get, "https://api.github.com/repos/" + Repository + "/releases/latest"))
        {
            request.Headers.UserAgent.ParseAdd("MinimalisticRadio/" + Current.ToString(3));
            request.Headers.Accept.ParseAdd("application/vnd.github+json");
            using (HttpResponseMessage response = await client.SendAsync(request))
            {
                if (response.StatusCode == System.Net.HttpStatusCode.NotFound) return null;
                response.EnsureSuccessStatusCode();
                var root = new JavaScriptSerializer { MaxJsonLength = 4 << 20 }
                    .DeserializeObject(await response.Content.ReadAsStringAsync()) as Dictionary<string, object>;
                if (root == null) return null;
                string Text(Dictionary<string, object> data, string key) => data.TryGetValue(key, out object value) ? value as string : null;
                var release = new Release { Tag = Text(root, "tag_name"), Page = Text(root, "html_url"), Notes = Text(root, "body") };
                release.Version = ParseVersion(release.Tag);
                if (release.Version == null) return null;
                if (root.TryGetValue("assets", out object assets) && assets is object[] list)
                    foreach (var asset in list.OfType<Dictionary<string, object>>())
                    {
                        string name = Text(asset, "name");
                        if (name == null || !name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) continue;
                        release.Download = Text(asset, "browser_download_url");
                        string digest = Text(asset, "digest");
                        if (digest != null && digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase))
                            release.Sha256 = digest.Substring(7);
                        break;
                    }
                return release;
            }
        }
    }

    // Downloads the release's exe and checks it against the SHA-256 published by GitHub.
    internal static async Task<string> Download(Release release, Action<int> progress)
    {
        if (release.Download == null || !release.Download.StartsWith("https://github.com/", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(Lang.T("Wydanie nie zawiera pliku programu.", "The release has no program file."));
        string file = Path.Combine(Path.GetTempPath(), "Minimalistic Radio " + release.Version.ToString(3) + ".exe");
        string actual;
        using (var client = new HttpClient { Timeout = TimeSpan.FromMinutes(2) })
        {
            client.DefaultRequestHeaders.UserAgent.ParseAdd("MinimalisticRadio/" + Current.ToString(3));
            using (HttpResponseMessage response = await client.GetAsync(release.Download, HttpCompletionOption.ResponseHeadersRead))
            {
                response.EnsureSuccessStatusCode();
                long total = response.Content.Headers.ContentLength ?? 0;
                using (Stream source = await response.Content.ReadAsStreamAsync())
                using (FileStream target = File.Create(file))
                using (SHA256 hash = SHA256.Create())
                {
                    var buffer = new byte[1 << 16];
                    long received = 0;
                    int read;
                    while ((read = await source.ReadAsync(buffer, 0, buffer.Length)) > 0)
                    {
                        hash.TransformBlock(buffer, 0, read, null, 0);
                        await target.WriteAsync(buffer, 0, read);
                        received += read;
                        if (total > 0) progress?.Invoke((int)Math.Min(100, received * 100 / total));
                    }
                    hash.TransformFinalBlock(new byte[0], 0, 0);
                    actual = BitConverter.ToString(hash.Hash).Replace("-", "");
                }
            }
        }
        if (release.Sha256 != null && !string.Equals(actual, release.Sha256, StringComparison.OrdinalIgnoreCase))
        {
            File.Delete(file);
            throw new InvalidDataException(Lang.T("Pobrany plik jest uszkodzony.", "The downloaded file is damaged."));
        }
        return file;
    }

    // A running exe can't be overwritten, but it can be renamed: the old one steps aside as *.old,
    // the new one takes its place and is started; the old copy is removed on the next start.
    internal static void Install(string downloaded)
    {
        string exe = Exe, old = exe + ".old";
        if (File.Exists(old)) File.Delete(old);
        File.Move(exe, old);
        try { File.Move(downloaded, exe); }
        catch
        {
            File.Move(old, exe);
            throw;
        }
        Process.Start(new ProcessStartInfo(exe, "--updated") { UseShellExecute = false })?.Dispose();
    }

    internal static void CleanUp()
    {
        try
        {
            string old = Exe + ".old";
            if (File.Exists(old)) File.Delete(old);
        }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { Debug.WriteLine(error); }
    }
}
