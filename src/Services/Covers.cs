using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

internal static class Covers
{
    private static readonly Dictionary<string, string> cache = new Dictionary<string, string>();

    // "Artist – Title" or "Artist - Title" → its parts; without a separator the whole text is the title.
    internal static void Split(string track, out string artist, out string title)
    {
        artist = null;
        title = track;
        if (string.IsNullOrEmpty(track)) return;
        foreach (string separator in new[] { " – ", " — ", " - " })
        {
            int index = track.IndexOf(separator, StringComparison.Ordinal);
            if (index > 0 && index + separator.Length < track.Length)
            {
                artist = track.Substring(0, index).Trim();
                title = track.Substring(index + separator.Length).Trim();
                return;
            }
        }
    }

    // Album art from the free iTunes Search API (no account or key). Results are cached per song;
    // a cover is used only when its artist matches, so a jingle never gets someone else's picture.
    internal static async Task<string> Find(HttpClient client, string track)
    {
        Split(track, out string artist, out string title);
        if (artist == null) return null;
        lock (cache)
            if (cache.TryGetValue(track, out string known)) return known;

        string found = null;
        try
        {
            string address = "https://itunes.apple.com/search?media=music&entity=song&limit=5&term=" +
                Uri.EscapeDataString(artist + " " + title);
            var root = new JavaScriptSerializer().DeserializeObject(await client.GetStringAsync(address)) as Dictionary<string, object>;
            if (root != null && root.TryGetValue("results", out object list) && list is object[] results)
                foreach (var item in results.OfType<Dictionary<string, object>>())
                {
                    string name = item.TryGetValue("artistName", out object value) ? value as string : null;
                    string picture = item.TryGetValue("artworkUrl100", out object url) ? url as string : null;
                    if (picture == null || !SameArtist(artist, name)) continue;
                    found = picture.Replace("100x100bb", "600x600bb");
                    break;
                }
        }
        catch (Exception error) when (error is HttpRequestException || error is TaskCanceledException ||
            error is ArgumentException || error is InvalidOperationException)
        {
            Debug.WriteLine(error);
            return null; // not cached: maybe it works next time
        }
        lock (cache) cache[track] = found;
        return found;
    }

    private static bool SameArtist(string wanted, string found)
    {
        if (string.IsNullOrEmpty(found)) return false;
        string Clean(string text) => new string(text.ToLowerInvariant().Where(char.IsLetterOrDigit).ToArray());
        // "ARIANA GRANDE / MAC MILLER": the first artist is enough.
        string first = Clean(wanted.Split(new[] { '/', ',', '&', '(', ';' }, 2)[0]);
        string other = Clean(found);
        return first.Length > 1 && other.Length > 1 && (other.Contains(first) || first.Contains(other));
    }
}
