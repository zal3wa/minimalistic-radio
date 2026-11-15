using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
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
    internal string Id, Name, Country, Url, ResolvedUrl, Logo, Codec, Tags;
    internal int Bitrate;
    internal bool Hls, Working = true;
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
        var seen = new HashSet<string>();
        return (await Fetch(client, route, token)).Where(entry => Playable(entry.Codec, entry.Hls) &&
            seen.Add(AddressOf(entry))).Take(30).ToArray();   // asked for 40: some are filtered out
    }

    // Our hand-picked stations (music, MP3/AAC), by radio-browser stationuuid so addresses and logos stay current.
    internal static readonly string[] RecommendedIds =
    {
        "2e6fabb2-9a10-4b2a-91ae-25a7d535e247",   // 102.7 KIIS FM Los Angeles
        "9245e3a5-bf69-4a08-8fac-3903a55043bf",   // Antyradio Hard
        "9617a958-0601-11e8-ae97-52543be04c81",   // Radio Paradise Main Mix
        "a509502d-1ba7-4d51-9791-0be5a7d5ec34",   // KEXP 90.3 Seattle
        "961e6cac-0601-11e8-ae97-52543be04c81",   // NTS Radio 1
        "c454908c-eb81-11e9-a96c-52543be04c81",   // FIP Groove
        "9625d631-0601-11e8-ae97-52543be04c81",   // Radio Swiss Jazz
        "9aa33d22-a6ef-11e9-a787-52543be04c81",   // Radio Swiss Classic
        "960cf833-0601-11e8-ae97-52543be04c81",   // SomaFM Groove Salad
        "960e4940-0601-11e8-ae97-52543be04c81"    // Ibiza Global Radio
    };

    internal sealed class SuggestionList
    {
        internal DirectoryStation[] Recommended, Popular;
        internal string Country;   // null: worldwide
        internal bool Complete;    // false: the popular request failed, so this is not kept for the run
    }

    // "Popular in your country": the country that goes with the radio's language, never from the IP address; null: worldwide.
    internal static string CurrentCountry() => CountryFor(Lang.Code, SystemCountry());

    // Where each of the radio's languages is spoken, its home country first. English isn't here: it keeps the system country.
    private static readonly Dictionary<string, string[]> LanguageCountries = new Dictionary<string, string[]>
    {
        ["pl"] = new[] { "PL" },
        ["de"] = new[] { "DE", "AT", "CH", "LI", "LU" },
        ["uk"] = new[] { "UA" },
        ["cs"] = new[] { "CZ" },
        ["es"] = new[] { "ES", "MX", "AR", "CO", "CL", "PE", "VE", "EC", "GT", "CU", "BO", "DO", "HN", "PY", "SV", "NI", "CR", "PA", "UY", "PR" },
        ["fr"] = new[] { "FR", "BE", "CH", "LU", "MC", "CA" },
        ["it"] = new[] { "IT", "CH", "SM" },
        ["pt"] = new[] { "PT", "BR", "AO", "MZ" }
    };

    // The system country if the language is spoken there (Spanish in Mexico: Mexico), otherwise the language's home
    // country (Polish in the USA: Poland). English, or a language not in the table, keeps the system country (null: unknown).
    internal static string CountryFor(string language, string systemCountry)
    {
        if (language == null || !LanguageCountries.TryGetValue(language, out string[] countries)) return systemCountry;
        return countries.Contains(systemCountry) ? systemCountry : countries[0];
    }

    // The country from the system settings ("Country or region"); null when unknown.
    static string SystemCountry()
    {
        // "Country or region" first (RegionInfo follows the regional format, which may differ), then RegionInfo.
        try
        {
            string code = Windows.System.UserProfile.GlobalizationPreferences.HomeGeographicRegion;
            if (IsCountryCode(code)) return code.ToUpperInvariant();
        }
        catch (Exception) { /* Older Windows: use RegionInfo. */ }
        try
        {
            string code = RegionInfo.CurrentRegion.TwoLetterISORegionName;
            if (IsCountryCode(code)) return code.ToUpperInvariant();
        }
        catch (Exception error) when (error is ArgumentException || error is CultureNotFoundException) { Debug.WriteLine(error); }
        return null;
    }

    static bool IsCountryCode(string code) => code != null && code.Length == 2 && code.All(letter => letter < 128 && char.IsLetter(letter)) &&
        !new[] { "IV", "XX", "ZZ" }.Contains(code.ToUpperInvariant());

    // Names like "-- # TOP 100 CHARTS ---" or "a,b,c,d,e": starts with a symbol, has "||", "#" or "***", or many commas.
    internal static bool LooksLikeSpam(string name)
    {
        name = (name ?? "").Trim();
        return name.Length == 0 || !char.IsLetterOrDigit(name[0]) || name.Contains("||") || name.Contains("#") ||
            name.Contains("***") || name.Count(letter => letter == ',') > 3;
    }

    // Names compared loosely: "Radio RMF FM" and "RMF FM" are one station. Lower case, no word "radio", letters and digits only.
    internal static string NameKey(string name) => new string(string.Join(" ", (name ?? "").ToLowerInvariant().Split((char[])null, StringSplitOptions.RemoveEmptyEntries)
        .Where(word => word != "radio")).Where(char.IsLetterOrDigit).ToArray());

    // The popular list as shown: playable, not already recommended, no duplicates, no spam, the first 15.
    internal static DirectoryStation[] CleanPopular(IEnumerable<DirectoryStation> popular, IEnumerable<DirectoryStation> recommended)
    {
        var names = new HashSet<string>(recommended.Select(entry => NameKey(entry.Name)));
        var streams = new HashSet<string>(recommended.Select(entry => StreamKey(AddressOf(entry))));
        // A name that is nothing but "Radio" has an empty key: it is not compared by name.
        return popular.Where(entry => Playable(entry.Codec, entry.Hls) && !LooksLikeSpam(entry.Name) &&
            (NameKey(entry.Name).Length == 0 || names.Add(NameKey(entry.Name))) & streams.Add(StreamKey(AddressOf(entry)))).Take(15).ToArray();
    }

    internal static async Task<SuggestionList> Suggestions(HttpClient client, CancellationToken token)
    {
        string country = CurrentCountry();
        List<DirectoryStation> fetched = await Fetch(client, "/json/stations/byuuid?uuids=" + string.Join(",", RecommendedIds), token);
        // In our order; a missing, broken or unplayable station is skipped.
        DirectoryStation[] recommended = RecommendedIds.Select(id => fetched.FirstOrDefault(entry => entry.Id == id))
            .Where(entry => entry != null && entry.Working && Playable(entry.Codec, entry.Hls)).ToArray();
        string route = "/json/stations/search?hidebroken=true&order=clickcount&reverse=true&limit=40" +
            (country == null ? "" : "&countrycode=" + country);
        DirectoryStation[] popular = new DirectoryStation[0];
        bool complete = true;
        try { popular = CleanPopular((await Fetch(client, route, token)).Where(entry => entry.Working), recommended); }
        catch (HttpRequestException error) { Debug.WriteLine(error); complete = false; }   // the recommended ones are still shown
        if (recommended.Length == 0 && popular.Length == 0)
            throw new HttpRequestException(Lang.T("Nie udało się połączyć z katalogiem stacji.", "Couldn't reach the station directory."));
        return new SuggestionList { Recommended = recommended, Popular = popular, Country = country, Complete = complete };
    }

    static string AddressOf(DirectoryStation entry) => IsWebUrl(entry.ResolvedUrl) ? entry.ResolvedUrl : entry.Url;

    // One request to the first server that answers (then the second): every station with a name and a web address.
    static async Task<List<DirectoryStation>> Fetch(HttpClient client, string route, CancellationToken token)
    {
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
                        var found = new List<DirectoryStation>();
                        foreach (var item in (items ?? new object[0]).OfType<Dictionary<string, object>>())
                        {
                            string Text(string key) => item.TryGetValue(key, out object value) ? value as string : null;
                            var entry = new DirectoryStation
                            {
                                Id = Text("stationuuid"), Name = Text("name"), Country = Text("country"), Url = Text("url"),
                                ResolvedUrl = Text("url_resolved"), Logo = Text("favicon"),
                                Codec = Text("codec"), Tags = Text("tags"),
                                Bitrate = item.TryGetValue("bitrate", out object bitrate) && bitrate is int rate ? rate : 0,
                                Hls = item.TryGetValue("hls", out object flag) && flag is int on && on == 1,
                                Working = !(item.TryGetValue("lastcheckok", out object ok) && ok is int check && check == 0)
                            };
                            if (!string.IsNullOrWhiteSpace(entry.Name) && IsWebUrl(AddressOf(entry))) found.Add(entry);
                        }
                        return found;
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
