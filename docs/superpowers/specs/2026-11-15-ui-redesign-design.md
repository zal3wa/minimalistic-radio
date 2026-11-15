# One look on every system: top bar, settings and Statistics

Approved by the owner on 2026-11-15 after a round of mockups. This spec is the written form of those mockups; when the
two disagree on a detail that is not written here, the mockups win.

- Top bar mockups: https://claude.ai/artifact/NFX2ooYExjbBGHosDHH6Uo (files `project/Windows.dc.html`,
  `project/Linux.dc.html`, `project/Mac.dc.html`; the "today" boards show the current apps).
- Settings and Statistics mockups: https://claude.ai/artifact/V7XidNaqm9x4VpbApoALYV (files
  `project/WinSettings.dc.html`, `project/LinuxSettings.dc.html`, `project/MacSettings.dc.html`).

The mockups are 1:1: one CSS pixel is one point at 100 % scaling.

## Why

The owner likes the Mac app's look best and wants the three apps (Windows, Linux, macOS) to look and behave the same,
each still with its own system's controls, fonts, colours and icons. On top of that, a new Statistics page.

## Goals

- The same top bar, subpage header, settings layout and Statistics page on Windows, Linux and macOS.
- Each system keeps its native look: WPF/Windows 11 on Windows, GTK 4/libadwaita on Linux, SwiftUI/AppKit on macOS.
- Statistics are collected and kept only on the computer; nothing is sent anywhere.

## Non-goals

- No new themes, no new settings beyond what is listed here.
- README and screenshot updates come later, after the owner has tried the builds.
- No releases: version numbers are bumped, but tags and releases wait for the owner's explicit OK.

## Shared layout

### Window size

The panel/window is **412 × 602** on all three systems. Windows and macOS already are; Linux changes its default size
from 380 × 640.

### Top bar on the stations page

Left to right:

1. **[+ Station]** button with a plus icon and the label "Station" (existing text). It opens the add-a-station
   search, as today.
2. **[History]** button with a history icon (clock with a counter-clockwise arrow) and the label "History" (new text on
   Linux and macOS; Windows already has it). It opens Song history.
3. Flexible space.
4. **Update ready** button, only when an update is ready: a green filled circle with a white down arrow
   (macOS: `arrow.down.circle.fill` in green, as today). Tooltip: the existing "Update to {0}" / "Update Ready!" text.
   Linux has no in-app updates, so no such button there.
5. **Settings** icon button (Windows: the existing sliders icon; Linux: `emblem-system-symbolic`; macOS: `gearshape`).
6. **Linux only:** a ✕ window close button (see Hiding below). Windows and macOS have **no** close/hide button.

Under the bar: a **1 px divider**, the theme's text colour at **10 %** opacity (light theme: dark line, dark theme: light
line), full width.

Spacing: the space above, below and to the left of [+ Station] is equal (Windows 12 px, macOS 10 px, Linux 9 px). The
icon buttons on the right end at the same inset from the right edge.

Removed:

- **Windows:** the row with the app icon and "Minimalistic Radio", the separate row with [+ Station], and the
  "Stations" heading. The list starts right under the bar (12 px gap).
- **Linux:** the plain "+" icon button, the truncated "Minimalistic Radio" title, and the minimize and maximize
  buttons (set the header bar's decoration layout so only close shows, regardless of the system setting).
- **macOS:** the magnifier button (the [+ Station] button already opens search).

History icons: Windows and Linux draw the Lucide `history` icon
(`M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5 M12 7v5l4 2`, stroke 2 on a 24 grid, round caps and joins).
Windows draws it like its other Lucide glyphs; Linux ships it as a symbolic SVG icon in the app's icon theme folder.
macOS uses `clock.arrow.circlepath`.

### Subpages (Song history, Settings, Statistics, Add a station, the station form)

The bar shows **‹ Title** on the left: a back button (Windows: the existing ← BackIcon; Linux: `go-previous-symbolic`;
macOS: `chevron.left`) and the page title, left-aligned, semibold (Windows 14 px, Linux 15 px bold, macOS 13 pt bold).
Linux also has the ✕ on the right. Same divider under it. Titles: "Song history", "Settings", "Statistics", and the
existing titles of the other pages.

**Song history** also has a **[Statistics]** button on the right of its bar *(the owner's request after 2.6.0)*: the
same labelled style as [+ Station] / [History], with a bar-chart icon (Windows and Linux: Lucide `chart-column`,
`M3 3v16a2 2 0 0 0 2 2h16 M18 17V9 M13 17V5 M8 17v-3`; macOS: `chart.bar`), label "Statistics". It opens the
Statistics page; ← (and Esc) from Statistics go back to the page it was opened from (Song history or Settings). On
Linux it sits left of the ✕.

Windows: the subpage title moves from the big heading row into the bar; Segoe UI sits low in its line box, so nudge
the title text up by 1 px (or otherwise centre it optically with the icons) — check it in the `--preview` pictures.

### The player (now playing card, volume, Play/Stop)

Shown **only on the stations page**. Song history, Settings, Statistics and the other subpages give that space to their
content (Linux already works this way). *(This was the recommended answer to an open question; the owner said "start"
without objecting. Easy to revert.)*

### Hiding the window

- **Windows and macOS:** the panel hides when it loses focus (a click elsewhere), on Esc, and on a click on the tray /
  menu bar icon — as today. There is no hide button in the bar anymore, so a click elsewhere must always close it
  (Windows 2.6.0 had a bug where it didn't).
- **Linux:** the window is a normal window. Its ✕ hides it (the radio keeps playing), tooltip "Close (the radio keeps
  playing)". The first time it is closed, show the notification "The radio keeps playing" (today it shows only when there
  is no tray icon; show it once in every case, then never again). Esc still hides it.

### Stations list

- **Windows:** the playing station's row also shows a filled play triangle in the accent colour before the ⋯ button
  (like Linux and macOS). The Play/Stop button's stop square is filled.
- **macOS:** the list's right inset equals its left inset (16 px): row separators and the ⋯ button end 16 px from the
  right edge (today SwiftUI's List adds about 33 px).
- Equal paddings: the space above the list equals the space at its sides (Windows 12 px, Linux 12 px).
- The footer's space under Play/Stop equals the space at its sides (12 px on all three).

### Song history

Each row starts with the **station's logo** (Windows 32 px, Linux 40 px, macOS 30 px; the same logo cache as the
stations list), then the song and "Station · time" under it, then ⋯. Match the station by name (the history stores the
station's name); a station that has no logo or is no longer on the list gets the list's placeholder icon.

## Settings page

Same order and structure on all three systems; each section is one card (one boxed group) with rows separated by thin
lines. **No row icons** (Windows drops its per-card icons). A row is: title, a grey description under it, the control on
the right.

1. **General** (header): Language (system default + languages); Start with Windows / Start with the system / Open at
   login (existing texts and descriptions); Show station changes (existing texts).
2. **Stations** (header): "Station list" with "A copy in a file, e.g. for friends"; under it, a second row with
   [Export…] [Import…] aligned right. Status messages after export/import stay as today.
3. **Statistics** card, **no header**, two rows *(the owner's later edit of the mockups)*:
   - title "Statistics", description "Collected only on this computer, never sent anywhere", and an **on/off toggle**
     (on by default). Off: nothing new is recorded (no sessions, no songs); what was collected stays.
   - under a divider: "Collected since {date}" (the first recorded session's day, the long date format of the UI
     language; "Nothing collected yet" when there is none) and the [Show] button on the right, which opens the
     Statistics page.
4. **Updates** (header), Windows and macOS only (Linux updates come through Flatpak): the toggle row titled
   **"Automatic updates"** *(the owner's later edit)* with "Looks for a new version every few hours", and a row "Last
   checked: …" with [Check now] (Windows: [Update] when one is ready, as today).
5. **About** (header): one row: the **app icon** (Windows/Linux: the round icon from `docs/icon.svg` /
   `linux/data/icons/.../io.github.zal3wa.minimalistic-radio.svg`, 32 px; macOS: the rounded-square app icon, 38 px),
   "Minimalistic Radio", description "Version X · MIT" (Windows keeps " · Lucide icons"), and a "GitHub ↗" link on the
   right to https://github.com/zal3wa/minimalistic-radio. Linux drops the chevron to the About dialog; macOS replaces its
   three About rows with this one.
6. **Quit** card, **no header** *(the owner's later edit of the mockups, replacing the button-only card)*: one row
   with the title "Quit", the description "Stops the radio and removes it from the tray" (macOS: "… from the menu
   bar"), and on the right a button "Quit" with red text (Windows: a normal button with red text `#C42B1C`/dark
   `#FF99A4`; Linux: the `destructive-action` style; macOS: a push button with the destructive role).

Windows keeps its "On/Off" text next to toggles. Linux keeps libadwaita rows (`Adw.PreferencesGroup`, `Adw.SwitchRow`,
`Adw.ComboRow`, `Adw.ActionRow`). macOS keeps `Form` with `.formStyle(.grouped)`.

## Statistics page

Opened from Settings › Statistics › [Show]. Title "Statistics". Content, top to bottom:

1. **Period switch**: three equal segments "All", "Year", "Month"; Month is selected when the page opens. Windows: a
   bordered group with the selected segment filled with the accent colour; Linux: a toggle group (libadwaita
   `Adw.ToggleGroup` where available, else linked toggle buttons); macOS: a segmented `Picker`.
2. **Listening time** card: label "Listening time" on the left and the period on the right ("November 2026", "2026",
   "Since 2 March 2025" — the system's date format for the UI language); the total in large type ("42 h 18 min");
   under it "≈ 2 h 49 min a day".
3. **Three tiles** in equal columns: "Song titles" (the number of song titles received), "Stations" (stations listened
   to), "Longest" (the longest single session). The label sits at the top, the value at the bottom, so values stay in one
   row even if a translated label wraps.
4. **Top stations** (header): up to 5 stations by listening time: logo, name, time on the right, and under the name a
   thin bar (6 px, rounded, accent colour) as long as the time relative to the first station.
5. **Top artists** (header) with a grey caption under it: "From song titles sent by the stations · 58% of listening
   time". Up to 5 artists by number of plays: rank, artist, "14 plays". If that share is under 20 %, show "Not enough
   song titles yet" instead of the list.
6. **When you listen** (header): a card with "Most often 20:00–21:00" (local time format) and 24 bars, one per hour of
   the day (00 … 23), heights proportional to the listening minutes in that hour, with labels 00, 06, 12, 18, 24 under
   them.
7. At the bottom, a link-style button "Clear statistics", asking for confirmation before it deletes the data.

With no data in the chosen period, the page shows the switch and one line: "Nothing here yet. Listen for a while and
come back."

When collecting is switched off, a grey line under the period switch says "Statistics are off. Nothing new is
recorded."; what was collected before is still shown.

### What is recorded, and how it is counted

A new file in the app's data folder, next to the history: `statistics.json` (UTF-8, written atomically like the other
files):

```json
{
  "version": 1,
  "sessions": [{ "station": "Antyradio Hard", "url": "https://…", "start": "2026-11-15T19:02:00Z", "end": "2026-11-15T20:41:30Z", "titles": true }],
  "songs": [{ "station": "Antyradio Hard", "title": "Leonard Cohen - Everybody Knows", "time": "2026-11-15T19:05:12Z" }]
}
```

- A **session** runs while a station is actually playing: it starts when audio starts and ends on Stop, a station
  change, the sleep timer, an error that stops playback, or quitting. A reconnect to the same station within 2 minutes
  continues the same session. A running session is saved every 5 minutes (its `end` updated), so a crash loses at most
  5 minutes. `titles` is true when the station sent at least one song title during the session.
- A **song** is recorded when the song history gets a new entry (same rules and filters as the history, so ads,
  station names and repeats are skipped). The artist is the part before the first " - "; titles without " - " count as
  song titles but not as artists.
- **Period**: Month = the current calendar month, Year = the current calendar year, All = everything; local time.
  Sessions that cross a boundary count only their part inside the period (also per hour for the histogram).
- **Per day**: the total divided by the days elapsed in the period (Month: today's day of the month; Year: today's day
  of the year; All: days since the first session, at least 1).
- **Time format**: under 1 hour "18 min"; under 100 hours "42 h 18 min"; from 100 hours "386 h".
- **Share for Top artists**: listening time of sessions with `titles` true, divided by all listening time in the period.
- **Logos**: from the current station list, by URL, then by name; otherwise the placeholder icon.
- The statistics are separate from the song history: "Clear history" doesn't clear them, "Clear statistics" doesn't
  clear the history. Removing a station keeps its statistics.

Keep the counting logic in each app's testable core (Windows: a plain class without WPF; Linux: `core/`; macOS:
`RadioCore`) and cover it with unit tests: period boundaries, sessions crossing midnight / month / year, reconnect
merging, the per-day average, the time format, top lists, the share and its 20 % threshold, the histogram.

## Texts

New English texts, translated into every catalogue the platform has (pl, de, uk, cs, es, fr, it, pt): History (Linux,
macOS), Statistics, Collected only on this computer, never sent anywhere, Show, All, Year, Month, Listening time, Since
{0}, ≈ {0} a day, the time formats, Song titles, Longest, Top stations, Top artists, From song titles sent by the
stations · {0} of listening time, Not enough song titles yet, {0} plays (with plural forms where the catalogue supports
them; otherwise a form that reads right with any number), When you listen, Most often {0}, Clear statistics, its
confirmation, Nothing here yet. Listen for a while and come back., Close (the radio keeps playing) (Linux).

## Versions

Windows 2.6.0 (`src/MinimalisticRadio.csproj`); Linux 1.0.0-beta.7 equivalent (follow `docs/BUILDING.md` and
`docs/LINUX-PUBLISHING.md` for where the version lives); macOS 1.0.0-beta.3 (the tag sets it; nothing to bump if the
build reads the tag). **No tags, no releases, no pushes to `main`** without the owner's OK.

## Left to the builder

Exact control types where a platform has several fitting ones, how the panel's pages are structured internally, file
locations inside each app, and test names — following each app's existing patterns.
