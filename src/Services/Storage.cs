using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

// Same JSON shape as earlier versions: [{"Name":…,"Url":…,"Logo":…}] and {"Volume":…,"LastPlayed":…}.
public sealed class SavedStation
{
    public string Name { get; set; }
    public string Url { get; set; }
    public string Logo { get; set; }
}

// Files from before 2.3.0 also have "Decoder" (the FFmpeg setting); JavaScriptSerializer skips unknown keys.
public sealed class Preferences
{
    public int Volume { get; set; }
    public string LastPlayed { get; set; }
    public string Language { get; set; }   // "auto", "pl", "en"
    public bool? CheckUpdates { get; set; }
    public DateTime? LastUpdateCheck { get; set; }
    public bool? ShowStationPopup { get; set; }
}

public sealed class HistoryEntry
{
    public string Title { get; set; }
    public string Station { get; set; }
    public DateTime Time { get; set; }
}

internal sealed class DirectoryStation
{
    internal string Name, Country, Url, ResolvedUrl, Logo, Codec, Tags;
    internal int Bitrate;
}

internal static class Storage
{
    internal static readonly string Folder = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Minimalistic Radio");
    internal static readonly string StationFile = Path.Combine(Folder, "stations.json");
    internal static readonly string PreferencesFile = Path.Combine(Folder, "preferences.json");
    internal static readonly string HistoryFile = Path.Combine(Folder, "history.json");

    internal static T Read<T>(string file) where T : class
    {
        try { return File.Exists(file) ? new JavaScriptSerializer().Deserialize<T>(File.ReadAllText(file)) : null; }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException ||
            error is ArgumentException || error is InvalidOperationException)
        {
            Debug.WriteLine(error);
            return null;
        }
    }

    // Throws IOException/UnauthorizedAccessException; the old file stays intact if writing fails.
    internal static void Write(string file, object data)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(file));
        string temporary = file + ".tmp";
        File.WriteAllText(temporary, new JavaScriptSerializer().Serialize(data));
        File.Copy(temporary, file, true);
        File.Delete(temporary);
    }

    internal static bool IsWebUrl(string value) =>
        Uri.TryCreate(value, UriKind.Absolute, out Uri uri) &&
        (uri.Scheme == Uri.UriSchemeHttps || uri.Scheme == Uri.UriSchemeHttp) &&
        uri.UserInfo.Length == 0;

    // The same stream written differently is still the same station: http/https, letter case of the
    // server name, a default port and a trailing slash don't matter.
    internal static string StreamKey(string url)
    {
        if (!Uri.TryCreate(url?.Trim(), UriKind.Absolute, out Uri uri)) return url?.Trim() ?? "";
        string port = uri.IsDefaultPort ? "" : ":" + uri.Port;
        return uri.Host.ToLowerInvariant() + port + uri.AbsolutePath.TrimEnd('/') + uri.Query;
    }

    internal static bool SameStream(string first, string second) => StreamKey(first) == StreamKey(second);

    // Versions before 2.3.0 could download FFmpeg (about 100 MB) into a subfolder; nothing uses it any more.
    // It may be missing or still in use: then it's left for the next start.
    internal static void RemoveOldFFmpeg()
    {
        string folder = Path.Combine(Folder, "ffmpeg");
        try { if (Directory.Exists(folder)) Directory.Delete(folder, true); }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { Debug.WriteLine(error); }
    }

    // Windows plays MP3 and AAC (also HE-AAC, "AAC+"), not HLS playlists or other formats (Ogg, FLAC…).
    // An unknown codec is often MP3 or AAC after all; if not, playing it says so.
    internal static bool Playable(string codec, bool hls)
    {
        if (hls) return false;
        switch ((codec ?? "").Trim().ToUpperInvariant())
        {
            case "MP3": case "AAC": case "AAC+": case "UNKNOWN": case "": return true;
            default: return false;
        }
    }

    // radio-browser.info: free community directory of internet radio stations.
    internal static async Task<DirectoryStation[]> Search(HttpClient client, string query, CancellationToken token)
    {
        string route = "/json/stations/search?hidebroken=true&limit=40&order=clickcount&reverse=true&name=" + Uri.EscapeDataString(query);
        foreach (string server in new[] { "de1.api.radio-browser.info", "nl1.api.radio-browser.info" })
        {
            try
            {
                using (var request = new HttpRequestMessage(HttpMethod.Get, "https://" + server + route))
                {
                    request.Headers.UserAgent.ParseAdd("MinimalisticRadio/2.0");
                    using (HttpResponseMessage response = await client.SendAsync(request, token))
                    {
                        response.EnsureSuccessStatusCode();
                        string json = await response.Content.ReadAsStringAsync();
                        var items = new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024 }.DeserializeObject(json) as object[];
                        var seen = new HashSet<string>();
                        var found = new List<DirectoryStation>();
                        foreach (var item in (items ?? new object[0]).OfType<Dictionary<string, object>>())
                        {
                            string Text(string key) => item.TryGetValue(key, out object value) ? value as string : null;
                            var entry = new DirectoryStation
                            {
                                Name = Text("name"), Country = Text("country"), Url = Text("url"),
                                ResolvedUrl = Text("url_resolved"), Logo = Text("favicon"),
                                Codec = Text("codec"), Tags = Text("tags"),
                                Bitrate = item.TryGetValue("bitrate", out object bitrate) && bitrate is int rate ? rate : 0
                            };
                            string address = IsWebUrl(entry.ResolvedUrl) ? entry.ResolvedUrl : entry.Url;
                            bool hls = item.TryGetValue("hls", out object flag) && flag is int on && on == 1;
                            if (!string.IsNullOrWhiteSpace(entry.Name) && IsWebUrl(address) && Playable(entry.Codec, hls) && seen.Add(address))
                                found.Add(entry);
                        }
                        return found.Take(30).ToArray();   // asked for 40: some are filtered out
                    }
                }
            }
            catch (Exception error) when (!token.IsCancellationRequested && (error is HttpRequestException ||
                error is ArgumentException || error is InvalidOperationException || error is OperationCanceledException))
            {
                Debug.WriteLine(error);
            }
        }
        throw new HttpRequestException(Lang.T("Nie udało się połączyć z katalogiem stacji.", "Couldn't reach the station directory."));
    }
}
