using System;
using System.Globalization;

// Polish or English. Follows Windows unless chosen in the settings.
internal static class Lang
{
    internal static readonly bool SystemPolish = DetectPolish();

    internal static string Setting = "auto";   // "auto", "pl" or "en"

    internal static bool Polish => Setting == "pl" || (Setting != "en" && SystemPolish);

    // The language the radio is using: "pl" or "en".
    internal static string Code => Polish ? "pl" : "en";

    internal static string T(string polish, string english) => Polish ? polish : english;

    // Like Store apps: the first supported language in the user's preferred languages
    // (Settings → Time & language), which can differ from the Windows display language.
    private static bool DetectPolish()
    {
        try
        {
            foreach (string tag in Windows.System.UserProfile.GlobalizationPreferences.Languages)
            {
                string language = tag.Split('-')[0].ToLowerInvariant();
                if (language == "pl") return true;
                if (language == "en") return false;
            }
        }
        catch (Exception) { /* Older Windows: fall back to the display language. */ }
        return CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "pl";
    }
}
