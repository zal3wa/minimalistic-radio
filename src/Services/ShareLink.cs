using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;

// A station shared as a link (Share in a station's ⋯ menu): https://minimalistic-radio.github.io/#n=…&u=…&l=… opens a
// page with "Open in Minimalistic Radio", which is minimalistic-radio://add?n=…&u=…&l=…. The query is form-encoded as
// URLSearchParams writes it: n = name, u = stream address, l = logo (optional); other keys are ignored. Plain C#
// without WPF, checked by the self-test. The part after # never reaches a server.
internal sealed class SharedStation
{
    internal string Name, Url, Logo;
}

internal static class ShareLink
{
    internal const string Page = "https://minimalistic-radio.github.io/";
    internal const string Scheme = "minimalistic-radio";

    private const string Host = "minimalistic-radio.github.io";
    private const int LongestAddress = 2048, LongestName = 100;

    // The link to send: the page, which opens the radio. The logo goes along only when the other side would keep it.
    internal static string Web(string name, string url, string logo) => Page + "#" + Query(name, url, logo);

    // The page's "Open in Minimalistic Radio".
    internal static string App(string name, string url, string logo) => Scheme + "://add?" + Query(name, url, logo);

    private static string Query(string name, string url, string logo)
    {
        string query = "n=" + Encode(name) + "&u=" + Encode(url);
        return Logo(logo) != null ? query + "&l=" + Encode(logo) : query;
    }

    // Is the text a share link at all: the page (with or without a station after #) or the radio's own link? Then
    // station is the station it carries, checked like the page checks it, or null when it carries none.
    internal static bool TryParse(string text, out SharedStation station)
    {
        station = null;
        text = text?.Trim() ?? "";
        string query;
        if (text.StartsWith(Scheme + ":", StringComparison.OrdinalIgnoreCase))
        {
            // minimalistic-radio://add?… (a browser may add a slash: //add/?…)
            string rest = text.Substring(Scheme.Length + 1);
            int question = rest.IndexOf('?');
            string action = (question < 0 ? rest : rest.Substring(0, question)).Trim('/');
            if (!action.Equals("add", StringComparison.OrdinalIgnoreCase)) return true;
            query = question < 0 ? "" : rest.Substring(question + 1);
        }
        else
        {
            // https://minimalistic-radio.github.io/#… (the part after # read as it was written, not as Uri tidies it)
            int hash = text.IndexOf('#');
            string address = hash < 0 ? text : text.Substring(0, hash);
            if (!Uri.TryCreate(address, UriKind.Absolute, out Uri uri) || (uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp) ||
                !uri.Host.Equals(Host, StringComparison.OrdinalIgnoreCase) || (uri.AbsolutePath != "/" && uri.AbsolutePath != "/index.html"))
                return false;
            query = hash < 0 ? "" : text.Substring(hash + 1);
        }
        var values = new Dictionary<string, string>();
        foreach (string pair in query.Split('&'))
        {
            if (pair.Length == 0) continue;
            int equals = pair.IndexOf('=');
            string key = Decode(equals < 0 ? pair : pair.Substring(0, equals)), value = equals < 0 ? "" : Decode(pair.Substring(equals + 1));
            if (!values.ContainsKey(key)) values[key] = value;   // the first one, as URLSearchParams.get gives it
        }
        values.TryGetValue("n", out string name);
        values.TryGetValue("u", out string url);
        values.TryGetValue("l", out string logo);
        name = Name(name);
        url = url?.Trim();
        // The radio's own rule for a stream address (no user name or password in it either), at most 2048 characters.
        if (name.Length == 0 || url == null || url.Length > LongestAddress || !Storage.IsWebUrl(url)) return true;
        station = new SharedStation { Name = name, Url = url, Logo = Logo(logo) };
        return true;
    }

    // Trimmed, without control characters, at most 100 characters (not cutting a character made of two halves).
    private static string Name(string name)
    {
        name = new string((name ?? "").Where(letter => !char.IsControl(letter)).ToArray()).Trim();
        if (name.Length <= LongestName) return name;
        int length = char.IsHighSurrogate(name[LongestName - 1]) ? LongestName - 1 : LongestName;
        return name.Substring(0, length).TrimEnd();
    }

    // A logo goes along and is kept as an absolute http or https address (the radio's own rule) of at most 2048
    // characters; the page shows an http one through https.
    private static string Logo(string logo)
    {
        logo = logo?.Trim();
        return logo != null && logo.Length <= LongestAddress && Storage.IsWebUrl(logo) ? logo : null;
    }

    // application/x-www-form-urlencoded as URLSearchParams writes it: letters, digits and *-._ as they are, a space
    // as +, everything else as %XX of its UTF-8 bytes.
    private static string Encode(string value)
    {
        var encoded = new StringBuilder();
        foreach (byte part in Encoding.UTF8.GetBytes(value ?? ""))
        {
            char letter = (char)part;
            if (letter < 128 && (char.IsLetterOrDigit(letter) || letter == '*' || letter == '-' || letter == '.' || letter == '_')) encoded.Append(letter);
            else if (letter == ' ') encoded.Append('+');
            else encoded.Append('%').Append(part.ToString("X2", CultureInfo.InvariantCulture));
        }
        return encoded.ToString();
    }

    // Both + and %20 are spaces; a % that doesn't start a valid escape stays as it is.
    private static string Decode(string value) => Uri.UnescapeDataString(value.Replace('+', ' '));

#if SELFTEST
    // Self-test (--test-menu): building and reading links, and what makes one invalid.
    internal static void Verify()
    {
        void Check(bool ok, string what)
        {
            if (!ok) throw new InvalidOperationException("Link do stacji: " + what);
        }
        SharedStation Read(string link) => TryParse(link, out SharedStation station) ? station : throw new InvalidOperationException("Link do stacji nierozpoznany: " + link);
        bool Invalid(string link) => TryParse(link, out SharedStation station) && station == null;

        // The spec's example, and the app link with the same query.
        const string hard = "https://an05.cdn.eurozet.pl/ANTHAR.mp3";
        Check(Web("Antyradio Hard", hard, null) == "https://minimalistic-radio.github.io/#n=Antyradio+Hard&u=https%3A%2F%2Fan05.cdn.eurozet.pl%2FANTHAR.mp3",
            "przykład ze specyfikacji: " + Web("Antyradio Hard", hard, null));
        Check(App("Antyradio Hard", hard, null) == "minimalistic-radio://add?n=Antyradio+Hard&u=https%3A%2F%2Fan05.cdn.eurozet.pl%2FANTHAR.mp3", "link do aplikacji.");
        // Encoded like URLSearchParams: letters, digits and *-._ stay, a space is +, the rest %XX (UTF-8).
        Check(Web("Radio ZET & Co. *~+#=", "https://a.example/x?y=1&z=2", "https://a.example/logo.png") ==
            Page + "#n=Radio+ZET+%26+Co.+*%7E%2B%23%3D&u=https%3A%2F%2Fa.example%2Fx%3Fy%3D1%26z%3D2&l=https%3A%2F%2Fa.example%2Flogo.png",
            "kodowanie znaków: " + Web("Radio ZET & Co. *~+#=", "https://a.example/x?y=1&z=2", "https://a.example/logo.png"));

        // Round trip, with Polish letters, an emoji and every special character.
        foreach (var (name, url, logo) in new[] { ("Radio Nowy Świat 😀 & +#%=?/", "https://stream.nowyswiat.online/mp3?a=1&b=%20", "https://dabplus.live/logo/x.png"),
            ("Antyradio Hard", hard, null) })
            foreach (string link in new[] { Web(name, url, logo), App(name, url, logo) })
            {
                SharedStation back = Read(link);
                Check(back != null && back.Name == name && back.Url == url && back.Logo == logo, "w obie strony: " + link);
            }

        // + and %20 are both spaces; the key's first value counts; unknown keys and an empty pair are ignored.
        Check(Read(Page + "#n=Radio%20357&u=https%3A%2F%2Fstream.radio357.pl%2F")?.Name == "Radio 357", "%20 jako spacja.");
        Check(Read(Page + "#n=Radio+357&x=1&&u=https://stream.radio357.pl/&n=Inna&v=2")?.Name == "Radio 357", "+ jako spacja, nieznane klucze, pierwsza wartość.");
        Check(Read(Page + "index.html#n=A&u=https%3A%2F%2Fa.example%2F")?.Url == "https://a.example/", "strona index.html.");
        Check(Read(Page + "#n=100%25+%zz%&u=https%3A%2F%2Fa.example%2F")?.Name == "100% %zz%", "% bez poprawnego kodu.");
        Check(Read("  MINIMALISTIC-RADIO://add/?n=A&u=http%3A%2F%2Fa.example%3A8000%2Flive  ")?.Url == "http://a.example:8000/live", "link do aplikacji pisany inaczej.");

        // Missing or bad keys: an invalid link (still recognised as one, so the page can say so).
        Check(Invalid(Page) && Invalid(Page + "#") && Invalid(Page + "#u=https%3A%2F%2Fa.example%2F") && Invalid(Page + "#n=A"), "brakujące klucze.");
        foreach (string bad in new[] { "ftp://a.example/x", "javascript:alert(1)", "/live", "a.example/live", "https://", "https://user:pass@a.example/x",
            "https://a.example/" + new string('x', 2048) })
            Check(Invalid(Page + "#n=A&u=" + Uri.EscapeDataString(bad)), "zły adres strumienia: " + bad);
        Check(Read(Page + "#n=A&u=https%3A%2F%2Fa.example%2F" + new string('x', 2048 - 18))?.Url.Length == 2048, "adres strumienia na granicy 2048 znaków.");
        Check(Invalid(Page + "#n=%20%09%0A&u=https%3A%2F%2Fa.example%2F") && Invalid("minimalistic-radio://other?n=A&u=https%3A%2F%2Fa.example%2F"),
            "pusta nazwa albo inna akcja.");
        // The name: trimmed, without control characters, at most 100 characters (an emoji isn't cut in half).
        Check(Read(Page + "#n=%20%20Radio%09Z%0AE%00T%20&u=https%3A%2F%2Fa.example%2F")?.Name == "RadioZET", "nazwa bez znaków sterujących.");
        Check(Read(Page + "#n=" + new string('a', 150) + "&u=https%3A%2F%2Fa.example%2F")?.Name == new string('a', 100), "nazwa skrócona do 100 znaków.");
        Check(Read(Web(new string('a', 99) + "😀", "https://a.example/", null))?.Name == new string('a', 99), "skracanie nie rozcina emoji.");
        // The logo: an absolute http or https address of at most 2048 characters goes along and is kept (the page shows an
        // http one through https); anything else is left out without making the link invalid.
        const string favicon = "http://www.my-radios.com/favicon.ico";
        Check(Web("A", "https://a.example/", favicon).EndsWith("&l=http%3A%2F%2Fwww.my-radios.com%2Ffavicon.ico") &&
            Read(Web("A", "https://a.example/", favicon))?.Logo == favicon &&
            Read(Page + "#n=A&u=https%3A%2F%2Fa.example%2F&l=http%3A%2F%2Fwww.my-radios.com%2Ffavicon.ico")?.Logo == favicon, "logo http.");
        Check(Read(Web("A", "https://a.example/", "https://a.example/" + new string('l', 2048 - 18)))?.Logo?.Length == 2048, "logo na granicy 2048 znaków.");
        foreach (string logo in new[] { "javascript:alert(1)", "ftp://a.example/l.png", "/l.png", "a.example/l.png", "https://user:pass@a.example/l.png",
            "https://a.example/" + new string('l', 2048) })
        {
            Check(!Web("A", "https://a.example/", logo).Contains("&l="), "zły adres logo w linku: " + logo);
            SharedStation station = Read(Page + "#n=A&u=https%3A%2F%2Fa.example%2F&l=" + Uri.EscapeDataString(logo));
            Check(station != null && station.Logo == null, "zły adres logo: " + logo);
        }

        // Not share links at all: other pages, other text.
        foreach (string text in new[] { "Radio 357", "https://example.com/#n=A&u=https%3A%2F%2Fa.example%2F", "https://minimalistic-radio.github.io.example.com/#n=A",
            "https://stream.radio357.pl/", "", null })
            Check(!TryParse(text, out _), "to nie jest link do stacji: " + text);

        // "Already on the list": the radio's stream comparison (scheme and host in any case, one trailing / or none).
        Check(Storage.SameStream("https://A.example/live/", "https://a.example/live") && Storage.SameStream("HTTPS://a.example/x", " https://a.example/x ") &&
            !Storage.SameStream("https://a.example/Live", "https://a.example/live") && !Storage.SameStream("https://a.example/x", "https://b.example/x"),
            "porównywanie adresów strumieni.");
    }
#endif
}
