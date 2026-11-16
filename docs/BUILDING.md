# Building Minimalistic Radio

## Requirements

- [.NET SDK](https://dotnet.microsoft.com/download) 8 or newer
- Windows 10/11 SDK (from the Visual Studio Installer or [standalone](https://developer.microsoft.com/windows/downloads/windows-sdk/)); only its `Windows.winmd` metadata is used

## Build and test

```
dotnet build src/MinimalisticRadio.csproj -c Release -o out
```

That is the exe people get (GitHub Actions builds it the same way). `out` holds only this one file, the newest build. The self-test and the README screenshots aren't in it: it ignores `--preview` and `--screenshot`, and exits with code 3 on `--test-menu`. They are in a separate test build:

```
dotnet build src/MinimalisticRadio.csproj -c Release -p:SelfTest=true -o out-test
```

- `out-test\Minimalistic Radio.exe --test-menu` runs the self-test (exit code 0 means OK; on failure the log is in `%TEMP%\MinimalisticRadio-test.log`). It works on stations in memory and saves nothing.
- `--test-menu --preview` also renders the panel, a station being dragged (also far along a long list), menu, settings, history, statistics (a year of sample listening, only in memory: this month, switched off, and everything), the station form, Add a station, a station's ⋯ menu (share-menu), "Link copied", the Shared station page (also for a link without a station) and station card into `%TEMP%\MinimalisticRadio-*.png`. Add `--lang de` (any language code) to run it in that language.
- `--test-menu --screenshot` renders the README screenshots (English UI) into `%TEMP%\MinimalisticRadio-shot-*.png`, always at 2× (192 DPI, so 864 × 1244 px for the panel) whatever the display scaling: each window is laid out for 2× first, so lines and text are sharp; copy them to `docs/screenshots` (without the `MinimalisticRadio-shot-` prefix). The `tray-menu` picture puts the real menu above a drawn corner of the Windows 11 taskbar, as wide as the Linux tray picture. `share-menu`, `link-copied` and `shared` show sharing a station (it copies a link to the clipboard). The `demo-*` pictures (stations, history, history-menu, statistics) are the frames of the landing page's animated demo, and `MinimalisticRadio-shot-demo-hotspots.json` gives, for each, the pixel centre of what the pointer clicks there, measured on the elements while they are drawn. The stations, songs and cover are the same as in the Linux pictures, and only in memory. Don't touch the mouse while it runs: the panel closes when it loses focus, and a hovered menu item shows up highlighted.

## Translations

The code is in English: each text goes through `L("…")` (`Lc("context", "…")` where one English word needs two translations, like the switch's "Off"; `Ln("{0} play", "{0} plays", n)` for a text with a number, whose catalog entry has `msgid_plural` and a `msgstr[n]` for each plural form of the catalog's `Plural-Forms` header) and is looked up in `src/Lang/<code>.po`, a gettext catalog whose msgid is the English text. The build puts every catalog into the exe compressed (about 3 KB each); a text missing from a catalog, or marked fuzzy, shows in English. To correct a translation, edit its `msgstr` in a text editor or Poedit. A new text in the code needs an entry in every catalog: the self-test lists the missing ones. The pictures of `--test-menu --preview --lang uk` show whether longer texts still fit.

## Releases

Pushing a `v*` tag builds the exe with GitHub Actions and publishes a release with `Minimalistic-Radio.exe`; the release notes come from the annotated tag's message. Bump `<Version>` in `src/MinimalisticRadio.csproj` first and update the size in the README title (Explorer's KB, rounded up, of the normal build, not the test build). Installed copies find the new release within a few hours and show the green update arrow.

## How it works

- The UI is WPF on **.NET Framework 4.8**, which is part of every Windows 10 and 11. That's why the exe is so small.
- MP3 and AAC (including HE-AAC/AAC+) are decoded by **Windows itself** through a `MediaStreamSource` (HE-AAC gets an explicit AudioSpecificConfig, otherwise Windows plays it mono and muffled). Other formats (Ogg/Opus, FLAC, HLS) aren't supported: the station search hides them, and such a station stops with a message saying so.
- A dropped connection is retried, waiting a bit longer each time, and after sleep the station connects again at once. When Windows reports the network back (or a new address, as when switching Wi-Fi), it connects right away instead of waiting, even if the retries ran out in the last 10 minutes.
- The "Add a station" page shows suggestions while the search box is empty: a hand-picked list (radio-browser `stationuuid`s in `Storage.RecommendedIds`) and the most popular stations of the country that goes with the radio's language (`Storage.CountryFor`, never the IP address): the system's "Country or region" if the language is spoken there, otherwise the language's home country; with English, the system's country, cleaned of spam and duplicates. They load once per run.
- Song titles come from the stream's ICY metadata; cover art from the iTunes Search API, used only when the artist matches.
- Windows media controls (Win+A, media keys, lock screen) are fed through `SystemMediaTransportControls`. A Start menu shortcut with the app's ID lets Windows and taskbar media players know the app.
- Updates: every 6 hours the latest GitHub release is checked and downloaded in the background; a click on the green arrow renames the running exe to `*.old`, puts the new one in its place and restarts.
- Statistics (Settings › Statistics): a session runs while a station plays (a reconnect to the same station within 2 minutes continues it) and is saved every 5 minutes; songs are recorded with the history's entries. Both go to `statistics.json` next to the history and never leave the computer. Switched off in Settings (kept in `preferences.json`), nothing new is recorded and what was collected stays. The counting (periods in local time, sessions over a period's edge, top lists, hours) is in `Services/Statistics.cs`, without WPF, and the self-test checks it.
- Sharing a station (its ⋯ menu › Share) copies `https://minimalistic-radio.github.io/#n=…&u=…&l=…`; that page's button opens `minimalistic-radio://add?…` (`Services/ShareLink.cs` builds and checks both). Every start writes the per-user handler for that scheme to `HKCU\Software\Classes\minimalistic-radio` (`"<exe>" --open "%1"`; the test build doesn't). A second start with `--open` hands the link to the running radio with `WM_COPYDATA` to a message-only window, which only the same user session can find, and exits; the running radio shows the Shared station page, which asks before adding or playing (a station already on the list just plays). A link pasted into + Station's search box or the stream address does the same.

## Project structure

```
src/
  Program.cs     startup, single instance
  Radio/         tray icon, menu and playback (RadioApp), the panel (RadioPanel), dragging stations (StationDrag), station card (RadioOsd), README pictures (RadioShots, test build only)
  Audio/         station connection, decoding by Windows
  Services/      cover art, updates, storage, listening statistics, Windows integration, language (Lang)
  Lang/          translations: one gettext catalog per language (pl, de, uk, cs, es, fr, it, pt)
  Theme/         colours and Windows 11 style controls
  Assets/        app icon (radio.ico) and the Lucide icons' licence
docs/            icon.svg (the icon's source), download button, README screenshots
tools/IconMaker  draws radio.ico in all sizes: dotnet run --project tools/IconMaker -- <folder>
```

## Linux: the banned-stations list

`data/banned-stations.json` is the one list of stations the radio never shows, shared with Windows. Meson cannot read outside `linux/`, so the Linux build installs a copy, `linux/data/banned-stations.json`. After editing the repo-root file, copy it over the Linux copy (`cp data/banned-stations.json linux/data/`); a unit test fails if the two differ.

## Linux

The Linux version is in `linux/` (Python, GTK 4, libadwaita and GStreamer). It never touches `src/`.

- **Unit tests** run anywhere with Python 3.12 or newer: `cd linux && python -m pytest -q` (install `pytest` first; use a venv at `linux/.venv`). They cover `core/` and `controller.py`, which don't import GTK.
- **Integration tests** (GStreamer playback against a local server, the window) need a Linux system with PyGObject, GTK and GStreamer: see the `integration` job of `.github/workflows/linux.yml` for the packages. Run them with `cd linux && dbus-run-session -- xvfb-run -a python3 -m pytest tests/integration -q`.
- **Meson build:** `meson setup _build linux --prefix "$PWD/_installed" && meson compile -C _build && meson test -C _build && meson install -C _build`. The installed app runs a quick check with `_installed/bin/minimalistic-radio --self-test`.
- **Flatpak:** `flatpak-builder --user --install --force-clean _flatpak linux/flatpak/io.github.zal3wa.minimalistic-radio.yml` (GNOME 51 runtime and SDK).
- **Snap:** `cd linux && snapcraft` (see `linux/snap/snapcraft.yaml`).
- **Translations:** `linux/po/*.po`, one catalogue per language, gettext domain `minimalistic-radio`. They are separate from the Windows catalogues in `src/Lang`.
- **Release:** bump `VERSION` in `linux/minimalistic_radio/__init__.py` and add a `<release>` to `linux/data/io.github.zal3wa.minimalistic-radio.metainfo.xml.in` first, then push an annotated tag `linux-vX.Y.Z` (pre-releases: `linux-vX.Y.Z-beta.N`). GitHub Actions builds the Flatpak and the Snap, publishes the Flatpak to the radio's own Flatpak repository on GitHub Pages (where installed copies get their updates), creates the release (never marked "latest") and publishes the Snap. Step by step, with the store accounts: [LINUX-PUBLISHING.md](LINUX-PUBLISHING.md). Beta testers: [LINUX-TEST-CHECKLIST.md](LINUX-TEST-CHECKLIST.md).

## macOS

The Mac version is in `macos/` (Swift: SwiftUI with AppKit for the menu bar item and its panels, AVFoundation, App Intents). It never touches `src/` or `linux/`.

- **Where it is built:** on GitHub's Mac runners (`.github/workflows/macos.yml`), on every push that touches `macos/`: core tests, a universal build, `--self-test`, the README pictures (`--screenshot DIR`, artifact `macos-screenshots`) and a DMG (artifact `Minimalistic-Radio-dmg`). The Xcode project is generated: `cd macos && xcodegen generate` (needs `brew install xcodegen librsvg`).
- **Core tests** (the radio's logic, a port of the Linux core with its tests): `swift test --package-path macos/Core`.
- **Texts:** English in the code as `L("…")`. After changing texts, run `python macos/tools/sync_po.py`: it fills `macos/Lang/<code>.po` from the Windows and Linux catalogues and lists what is still to translate. Shortcuts and Siri texts are generated from the same catalogues at build time (`macos/tools/intents_strings.py`).
- **Releases:** a tag `macos-vX.Y.Z` (betas `macos-vX.Y.Z-beta.N`), signed with the project's own certificate: [MACOS-PUBLISHING.md](MACOS-PUBLISHING.md). Testers: [MACOS-TEST-CHECKLIST.md](MACOS-TEST-CHECKLIST.md).
