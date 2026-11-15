# Station suggestions: design

Date: 2026-11-14. Status: approved by the owner. Applies to Windows (2.4.0) and Linux (search page, Task 12 of the Linux plan).

## Intent

Users say they don't know any good stations. When the "Add a station" page opens with an empty search box, it shows suggestions to add with one click instead of an empty list.

## What the user sees

With the search box empty, the page lists two sections, using the same rows as search results (logo, name, "country · codec bitrate · tags", and `+` or a greyed ✓ "Already on your list"):

1. **Recommended** (PL "Polecane"): our hand-picked list, in this order.
2. **Popular in your country** (PL "Popularne w Twoim kraju"), or **Popular worldwide** (PL "Popularne na świecie") when the country is unknown.

Typing a search replaces both sections with results; clearing the box brings them back.

## Recommended stations

Valuable, international, music stations (the owner's wish), all MP3/AAC so Windows plays them. They are identified by radio-browser `stationuuid`, so their addresses and logos stay current.

| # | Station | Music | stationuuid |
|---|---|---|---|
| 1 | 102.7 KIIS FM Los Angeles | pop hits | 2e6fabb2-9a10-4b2a-91ae-25a7d535e247 |
| 2 | Antyradio Hard | hard rock | 9245e3a5-bf69-4a08-8fac-3903a55043bf |
| 3 | Radio Paradise Main Mix | eclectic rock | 9617a958-0601-11e8-ae97-52543be04c81 |
| 4 | KEXP 90.3 Seattle | indie | a509502d-1ba7-4d51-9791-0be5a7d5ec34 |
| 5 | NTS Radio 1 | eclectic, underground | 961e6cac-0601-11e8-ae97-52543be04c81 |
| 6 | FIP Groove | funk, soul, hip-hop | c454908c-eb81-11e9-a96c-52543be04c81 |
| 7 | Radio Swiss Jazz | jazz | 9625d631-0601-11e8-ae97-52543be04c81 |
| 8 | Radio Swiss Classic | classical | 9aa33d22-a6ef-11e9-a787-52543be04c81 |
| 9 | SomaFM Groove Salad | chillout | 960cf833-0601-11e8-ae97-52543be04c81 |
| 10 | Ibiza Global Radio | electronic | 960e4940-0601-11e8-ae97-52543be04c81 |

Fetched with one request: `/json/stations/byuuid?uuids=<comma-separated>`. Shown in the table's order. A station that's missing, broken (`lastcheckok` 0) or, on Windows, not playable is skipped.

## Popular in your country

- **Country:** from the system settings only, never from the IP address. On Windows, `RegionInfo.CurrentRegion` ("Country or region" in Settings); on Linux, the territory of the locale (`pl_PL.UTF-8` → `PL`). Invalid or neutral values mean the country is unknown.
- **Request:** `/json/stations/search?countrycode=<CC>&hidebroken=true&order=clickcount&reverse=true&limit=40`. Without a country, drop `countrycode`.
- **Clean-up, in order:** keep only playable stations (Windows: the existing `Playable` rule); drop stations already among Recommended (same stream or same name); drop duplicates by name (case-insensitive, trimmed) and by stream; drop spam-looking names (below); keep the first 15.
- **Spam-looking name:** it starts with a character that isn't a letter or digit, contains `||`, `#` or `***`, or has more than 3 commas.

## Behaviour

- Both lists load the first time the page opens and stay in memory until the radio quits. No reload on every open.
- They use the same two radio-browser servers as search, with the same fallback.
- While loading, show the existing "Searching…"-style status, worded "Loading suggestions…" (PL "Wczytuję propozycje…").
- If the directory can't be reached, show "Couldn't reach the station directory. Try again." The search still works.
- Adding a suggestion is the same as adding a search result.

## Privacy

README: radio-browser.info is contacted "when you open the station search or search for stations" (it gets your country code and what you typed).

## Not doing

Genre chips, more sections, IP geolocation, per-user personalisation.

## Approaches considered

- **Only our list:** no maintenance surprises, but nothing local. Rejected by the owner.
- **Only popular lists:** zero maintenance, but spammy entries and duplicates at the top. Rejected.
- **Both (chosen):** a curated international list plus local popularity, cleaned up.

Hidden stations (owner decision): Radio Republika (host radiotvrepublika.pl / tvrepublika.pl, or a PL station named Republika) never appears in search or suggestions.
