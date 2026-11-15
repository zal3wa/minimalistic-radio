# More languages, and the country for popular stations: design

Date: 2026-11-15. Status: approved by the owner. Applies to Windows and Linux.

## 1. The country for "Popular in your country" (Windows 2.4.0, Linux Task 12)

The owner's Windows is in Polish with "Country or region" set to the USA, and saw US stations. The country now follows the radio's language:

- Take the language the radio is using: the one chosen in Settings, or, with "Same as Windows"/"Same as system", the one detected from the system.
- If that language is English: use the system country (Windows "Country or region"; on Linux, the locale's territory). If that is unknown, use "Popular worldwide".
- Otherwise, if the system country is a country where that language is spoken, use the system country. For example, Spanish with Mexico gives Mexico.
- Otherwise use the language's home country.

| Language | Countries it is spoken in (system country kept) | Home country |
|---|---|---|
| pl | PL | PL |
| de | DE, AT, CH, LI, LU | DE |
| uk | UA | UA |
| cs | CZ | CZ |
| es | ES, MX, AR, CO, CL, PE, VE, EC, GT, CU, BO, DO, HN, PY, SV, NI, CR, PA, UY, PR | ES |
| fr | FR, BE, CH, LU, MC, CA | FR |
| it | IT, CH, SM | IT |
| pt | PT, BR, AO, MZ | PT |

Example: the owner's case (Polish, USA) gives PL.

## 2. More languages (Windows 2.5.0, Linux before 1.0.0)

- **Languages:** English (source), Polish, German, Ukrainian, Czech, Spanish, French, Italian, Portuguese. No Russian. The owner chose these.
- **Choosing the language:** the language setting lists "Same as Windows"/"Same as system" plus each language by its own name (Polski, Deutsch, Українська, Čeština, Español, Français, Italiano, Português, English). The automatic choice is the first supported language in the system's preferred languages (Windows `GlobalizationPreferences.Languages`; Linux `GLib.get_language_names()`), falling back to English.
- **Format:** gettext `.po` files on both platforms, so translators edit the same kind of file. English is the msgid.
  - Linux keeps `linux/po/<lang>.po` (Meson).
  - Windows gets `src/Lang/<lang>.po`. These files are embedded in the exe compressed (deflate) and parsed at startup by a small reader for `msgid`/`msgstr`, with no plural forms needed.
- **Windows code:** every `T("polski", "English")` becomes `L("English")`, looked up in the current catalog. `pl.po` is generated from the existing pairs, so the Polish wording stays exactly as it is.
- **Translations:** the assistant drafts them, natural and short, matching each platform's UI conventions (e.g. "Ustawienia"). Strings shared by both platforms are translated identically. The README invites native speakers to correct them.
- **Size:** Windows grows by the compressed catalogs only. The target is under +30 KB. The README title is updated.
- **Fallback:** a string missing from a catalog shows in English.

## Not doing

Russian. Right-to-left languages. Translating station names or song titles. A hosted translation service, which can come later.
