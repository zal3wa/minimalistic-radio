using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
#if SELFTEST
using System.Text.RegularExpressions;
#endif

// The radio's languages. The code is in English, and L looks each text up in the catalog of the language in use,
// src/Lang/<code>.po (gettext, the English text is the msgid), which is in the exe compressed and read when first
// needed. A text missing from the catalog shows in English. Follows Windows unless chosen in the settings.
internal static class Lang
{
    // In the order of the settings' list, each by its own name.
    internal static readonly (string Code, string Name)[] Languages =
    {
        ("pl", "Polski"), ("en", "English"), ("de", "Deutsch"), ("uk", "Українська"), ("cs", "Čeština"),
        ("es", "Español"), ("fr", "Français"), ("it", "Italiano"), ("pt", "Português")
    };

    internal static readonly string SystemLanguage = Detect();

    internal static string Setting = "auto";   // "auto" or a code from Languages

    // The language the radio is using.
    internal static string Code => IsSupported(Setting) ? Setting : SystemLanguage;

    internal static bool IsSupported(string code) => Languages.Any(item => item.Code == code);

    // Dates in the panel (history, last update check) in the radio's language.
    internal static CultureInfo Culture => CultureInfo.GetCultureInfo(Code == "en" ? "en-US" : Code == "uk" ? "uk-UA" :
        Code == "cs" ? "cs-CZ" : Code == "pt" ? "pt-PT" : Code + "-" + Code.ToUpperInvariant());

    // The text in the radio's language. With values, {0}, {1}… are filled in as by string.Format.
    internal static string L(string english, params object[] values) => Format(Translate(english, english), english, values);

    // The same for a text that needs a context (msgctxt) to tell it apart: the switch's "Off" isn't the sleep timer's.
    internal static string Lc(string context, string english, params object[] values) =>
        Format(Translate(context + "\u0004" + english, english), english, values);

    // A language's name in the radio's language ("In Windows: German").
    internal static string LanguageName(string code)
    {
        switch (code)
        {
            case "pl": return L("Polish");
            case "de": return L("German");
            case "uk": return L("Ukrainian");
            case "cs": return L("Czech");
            case "es": return L("Spanish");
            case "fr": return L("French");
            case "it": return L("Italian");
            case "pt": return L("Portuguese");
            default: return L("English");
        }
    }

    private static string Translate(string key, string english) =>
        Code != "en" && Catalog(Code).TryGetValue(key, out string text) ? text : english;

    private static string Format(string text, string english, object[] values)
    {
        if (values == null || values.Length == 0) return text;
        try { return string.Format(text, values); }
        catch (FormatException) { return string.Format(english, values); }   // a translation with a broken {0}
    }

    private static readonly Dictionary<string, Dictionary<string, string>> catalogs = new Dictionary<string, Dictionary<string, string>>();

    // Each catalog is read once. Texts are also asked for on other threads (a station's connection errors).
    private static Dictionary<string, string> Catalog(string code)
    {
        lock (catalogs)
        {
            if (catalogs.TryGetValue(code, out Dictionary<string, string> catalog)) return catalog;
            catalog = new Dictionary<string, string>();
            try
            {
                using (Stream packed = typeof(Lang).Assembly.GetManifestResourceStream("Lang." + code))
                    if (packed != null)
                        using (var reader = new StreamReader(new DeflateStream(packed, CompressionMode.Decompress), Encoding.UTF8))
                            catalog = Read(reader);
            }
            catch (Exception error) when (error is IOException || error is InvalidDataException) { Debug.WriteLine(error); }
            catalogs[code] = catalog;
            return catalog;
        }
    }

    // A gettext catalog: msgid (after its msgctxt, if any) → msgstr, with strings over several lines and the usual
    // escapes; no plural forms. Empty and fuzzy translations are left out, so those texts show in English.
    private static Dictionary<string, string> Read(TextReader reader)
    {
        var catalog = new Dictionary<string, string>();
        StringBuilder context = null, id = null, text = null, part = null;
        bool fuzzy = false;
        for (string line; (line = reader.ReadLine()) != null;)
        {
            line = line.Trim();
            // The msgstr ends at the first line that doesn't go on with it.
            if (text != null && !line.StartsWith("\""))
            {
                if (id?.Length > 0 && text.Length > 0 && !fuzzy)
                    catalog[(context == null ? "" : context + "\u0004") + id] = text.ToString();
                context = id = text = part = null;
                fuzzy = false;
            }
            if (line.StartsWith("#,")) fuzzy |= line.Contains("fuzzy");
            else if (line.StartsWith("msgctxt ")) part = context = new StringBuilder(Unquote(line.Substring(8)));
            else if (line.StartsWith("msgid ")) part = id = new StringBuilder(Unquote(line.Substring(6)));
            else if (line.StartsWith("msgstr ")) part = text = new StringBuilder(Unquote(line.Substring(7)));
            else if (line.StartsWith("\"")) part?.Append(Unquote(line));
            else part = null;   // a comment, a blank line, msgid_plural…
        }
        if (text != null && id?.Length > 0 && text.Length > 0 && !fuzzy)
            catalog[(context == null ? "" : context + "\u0004") + id] = text.ToString();
        return catalog;
    }

    // "text" in a catalog: \n, \t, \r, and a backslash before any other letter keeps that letter (\" and \\).
    private static string Unquote(string quoted)
    {
        quoted = quoted.Trim();
        if (quoted.Length < 2 || quoted[0] != '"' || quoted[quoted.Length - 1] != '"') return "";
        var text = new StringBuilder(quoted.Length);
        for (int i = 1; i < quoted.Length - 1; i++)
        {
            char letter = quoted[i];
            if (letter == '\\' && i + 1 < quoted.Length - 1)
            {
                letter = quoted[++i];
                letter = letter == 'n' ? '\n' : letter == 't' ? '\t' : letter == 'r' ? '\r' : letter;
            }
            text.Append(letter);
        }
        return text.ToString();
    }

    // Like Store apps: the first supported language in the user's preferred languages (Settings → Time & language),
    // which can differ from the Windows display language. English if none of them is supported.
    private static string Detect()
    {
        try
        {
            foreach (string tag in Windows.System.UserProfile.GlobalizationPreferences.Languages)
            {
                string language = tag.Split('-')[0].ToLowerInvariant();
                if (IsSupported(language)) return language;
            }
        }
        catch (Exception) { /* Older Windows: fall back to the display language. */ }
        string display = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName;
        return IsSupported(display) ? display : "en";
    }

#if SELFTEST
    // Self-test (--test-menu): every catalog loads and translates every text the code gives to L and Lc (the test
    // build carries the code for this, see the .csproj), and a text no catalog knows shows in English.
    internal static void Verify()
    {
        var assembly = typeof(Lang).Assembly;
        const string quoted = "\"((?:[^\"\\\\]|\\\\.)*)\"";
        var used = new HashSet<string>();
        foreach (string name in assembly.GetManifestResourceNames().Where(name => name.StartsWith("Source/")))
            using (var reader = new StreamReader(assembly.GetManifestResourceStream(name)))
                foreach (Match call in Regex.Matches(reader.ReadToEnd(), @"\bL(c?)\(" + quoted + @"(?:\s*,\s*" + quoted + ")?"))
                    used.Add(call.Groups[1].Length == 0 ? Regex.Unescape(call.Groups[2].Value)
                        : Regex.Unescape(call.Groups[2].Value) + "\u0004" + Regex.Unescape(call.Groups[3].Value));
        if (used.Count < 100)
            throw new InvalidOperationException("Za mało tekstów do tłumaczenia w kodzie: " + used.Count);
        var missing = new List<string>();
        foreach (var (code, _) in Languages.Where(item => item.Code != "en"))
        {
            Dictionary<string, string> catalog = Catalog(code);
            if (catalog.Count == 0) missing.Add(code + ": nie wczytał się katalog");
            else missing.AddRange(used.Where(text => !catalog.ContainsKey(text)).OrderBy(text => text)
                .Select(text => code + ": " + text.Replace("\u0004", " | ")));
        }
        if (missing.Count > 0)
            throw new InvalidOperationException("Brakujące tłumaczenia (" + missing.Count + "):\n" + string.Join("\n", missing));
        string saved = Setting;
        try
        {
            Setting = "de";
            string unknown = "Self-test " + Guid.NewGuid();
            if (L(unknown) != unknown || L("Settings") != "Einstellungen")
                throw new InvalidOperationException("Błędne wyszukiwanie w katalogu lub brak powrotu do angielskiego.");
        }
        finally { Setting = saved; }
    }
#endif
}
