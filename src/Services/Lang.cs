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

    // A text with a number, in the form the language needs for it: Ln("{0} play", "{0} plays", 3) is "3 plays", in
    // Polish "3 odtworzenia". {0} is the number. The catalog has the forms as msgstr[0], msgstr[1]…
    internal static string Ln(string singular, string plural, long count)
    {
        string english = count == 1 ? singular : plural;
        string text = Code != "en" && Catalog(Code).TryGetValue(singular + "\u0001" + PluralForm(Code, count), out string found) ? found : english;
        return Format(text, english, new object[] { count });
    }

    // Which msgstr[n] a number takes, as each catalog's Plural-Forms header says.
    internal static int PluralForm(string code, long count)
    {
        long n = Math.Abs(count);
        bool few = n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20);
        switch (code)
        {
            case "pl": return n == 1 ? 0 : few ? 1 : 2;
            case "uk": return n % 10 == 1 && n % 100 != 11 ? 0 : few ? 1 : 2;
            case "cs": return n == 1 ? 0 : n >= 2 && n <= 4 ? 1 : 2;
            case "fr": return n > 1 ? 1 : 0;
            default: return n == 1 ? 0 : 1;   // English, German, Spanish, Italian, Portuguese
        }
    }

    internal static int PluralForms(string code) => code == "pl" || code == "uk" || code == "cs" ? 3 : 2;

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
    // escapes. A text with plural forms (msgid_plural) has its msgstr[n] under msgid + "\u0001" + n. Empty and fuzzy
    // translations are left out, so those texts show in English.
    private static Dictionary<string, string> Read(TextReader reader)
    {
        var catalog = new Dictionary<string, string>();
        StringBuilder context = null, id = null, part = null;
        var texts = new SortedDictionary<int, StringBuilder>();   // msgstr (-1), or each msgstr[n]
        bool fuzzy = false;
        void Keep()
        {
            if (id?.Length > 0 && !fuzzy)
                foreach (var text in texts.Where(item => item.Value.Length > 0))
                    catalog[(context == null ? "" : context + "\u0004") + id + (text.Key < 0 ? "" : "\u0001" + text.Key)] = text.Value.ToString();
            context = id = part = null;
            texts.Clear();
            fuzzy = false;
        }
        for (string line; (line = reader.ReadLine()) != null;)
        {
            line = line.Trim();
            // The translation ends at the first line that doesn't go on with it (or with its next plural form).
            if (texts.Count > 0 && !line.StartsWith("\"") && !line.StartsWith("msgstr[")) Keep();
            int close = line.IndexOf(']');
            if (line.StartsWith("#,")) fuzzy |= line.Contains("fuzzy");
            else if (line.StartsWith("msgctxt ")) part = context = new StringBuilder(Unquote(line.Substring(8)));
            else if (line.StartsWith("msgid ")) part = id = new StringBuilder(Unquote(line.Substring(6)));
            else if (line.StartsWith("msgstr ")) part = texts[-1] = new StringBuilder(Unquote(line.Substring(7)));
            else if (line.StartsWith("msgstr[") && close > 7 && int.TryParse(line.Substring(7, close - 7), out int form) && form >= 0)
                part = texts[form] = new StringBuilder(Unquote(line.Substring(close + 1)));
            else if (line.StartsWith("\"")) part?.Append(Unquote(line));
            else part = null;   // a comment, a blank line, msgid_plural…
        }
        Keep();
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
        var plurals = new HashSet<string>();   // Ln's texts: each needs every plural form of each language
        foreach (string name in assembly.GetManifestResourceNames().Where(name => name.StartsWith("Source/")))
            using (var reader = new StreamReader(assembly.GetManifestResourceStream(name)))
            {
                string source = reader.ReadToEnd();
                foreach (Match call in Regex.Matches(source, @"\bL(c?)\(" + quoted + @"(?:\s*,\s*" + quoted + ")?"))
                    used.Add(call.Groups[1].Length == 0 ? Regex.Unescape(call.Groups[2].Value)
                        : Regex.Unescape(call.Groups[2].Value) + "\u0004" + Regex.Unescape(call.Groups[3].Value));
                foreach (Match call in Regex.Matches(source, @"\bLn\(" + quoted + @"\s*,\s*" + quoted))
                    plurals.Add(Regex.Unescape(call.Groups[1].Value));
            }
        if (used.Count < 100 || plurals.Count == 0)
            throw new InvalidOperationException("Za mało tekstów do tłumaczenia w kodzie: " + used.Count + " + " + plurals.Count);
        var missing = new List<string>();
        foreach (var (code, _) in Languages.Where(item => item.Code != "en"))
        {
            Dictionary<string, string> catalog = Catalog(code);
            if (catalog.Count == 0) missing.Add(code + ": nie wczytał się katalog");
            else missing.AddRange(used.Concat(plurals.SelectMany(text => Enumerable.Range(0, PluralForms(code)).Select(form => text + "\u0001" + form)))
                .Where(text => !catalog.ContainsKey(text)).OrderBy(text => text)
                .Select(text => code + ": " + text.Replace("\u0004", " | ").Replace("\u0001", " [") + (text.Contains("\u0001") ? "]" : "")));
        }
        if (missing.Count > 0)
            throw new InvalidOperationException("Brakujące tłumaczenia (" + missing.Count + "):\n" + string.Join("\n", missing));
        // Plural forms as each catalog's Plural-Forms header says.
        foreach (var (code, numbers) in new (string, string)[] { ("pl", "1:0 2:1 4:1 5:2 0:2 12:2 22:1 25:2 102:1 112:2"),
            ("uk", "1:0 21:0 11:2 3:1 13:2 24:1 5:2"), ("cs", "1:0 2:1 4:1 5:2 0:2"), ("fr", "0:0 1:0 2:1"), ("de", "1:0 0:1 2:1"), ("en", "1:0 2:1") })
            foreach (string pair in numbers.Split(' '))
                if (PluralForm(code, long.Parse(pair.Split(':')[0])) != int.Parse(pair.Split(':')[1]))
                    throw new InvalidOperationException($"Błędna forma liczby mnogiej: {code} {pair}.");
        string saved = Setting;
        try
        {
            Setting = "de";
            string unknown = "Self-test " + Guid.NewGuid();
            if (L(unknown) != unknown || L("Settings") != "Einstellungen")
                throw new InvalidOperationException("Błędne wyszukiwanie w katalogu lub brak powrotu do angielskiego.");
            Setting = "pl";
            string polish = string.Join("|", new[] { 1, 3, 5, 22 }.Select(count => Ln("{0} play", "{0} plays", count)));
            Setting = "en";
            string english = string.Join("|", new[] { 1, 14 }.Select(count => Ln("{0} play", "{0} plays", count)));
            if (polish != "1 odtworzenie|3 odtworzenia|5 odtworzeń|22 odtworzenia" || english != "1 play|14 plays")
                throw new InvalidOperationException("Błędna liczba mnoga: " + polish + ", " + english);
        }
        finally { Setting = saved; }
    }
#endif
}
