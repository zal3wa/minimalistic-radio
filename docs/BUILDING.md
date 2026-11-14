# Building Minimalistic Radio

## Requirements

- [.NET SDK](https://dotnet.microsoft.com/download) 8 or newer
- Windows 10/11 SDK (from the Visual Studio Installer or [standalone](https://developer.microsoft.com/windows/downloads/windows-sdk/)); only its `Windows.winmd` metadata is used

## Build and test

```
dotnet build src/MinimalisticRadio.csproj -c Release -o out
```

That is the exe people get (GitHub Actions builds it the same way). The self-test and the README screenshots aren't in it: it ignores `--preview` and `--screenshot`, and exits with code 3 on `--test-menu`. They are in a separate test build:

```
dotnet build src/MinimalisticRadio.csproj -c Release -p:SelfTest=true -o out\selftest
```

- `out\selftest\Minimalistic Radio.exe --test-menu` runs the self-test (exit code 0 means OK; on failure the log is in `%TEMP%\MinimalisticRadio-test.log`). It works on stations in memory and saves nothing.
- `--test-menu --preview` also renders the panel, a station being dragged (also far along a long list), menu, settings, history and station card into `%TEMP%\MinimalisticRadio-*.png`.
- `--test-menu --screenshot` renders the README screenshots (English UI) into `%TEMP%\MinimalisticRadio-shot-*.png`; copy them to `docs/screenshots`. The two `tray-*` pictures put the real menu and panel above a drawn corner of the Windows 11 taskbar.

## Releases

Pushing a `v*` tag builds the exe with GitHub Actions and publishes a release with `Minimalistic-Radio.exe`; the release notes come from the annotated tag's message. Bump `<Version>` in `src/MinimalisticRadio.csproj` first and update the size in the README title (Explorer's KB, rounded up, of the normal build, not the test build). Installed copies find the new release within a few hours and show the green update arrow.

## How it works

- The UI is WPF on **.NET Framework 4.8**, which is part of every Windows 10 and 11. That's why the exe is so small.
- MP3 and AAC (including HE-AAC/AAC+) are decoded by **Windows itself** through a `MediaStreamSource` (HE-AAC gets an explicit AudioSpecificConfig, otherwise Windows plays it mono and muffled). Other formats (Ogg/Opus, FLAC, HLS) aren't supported: the station search hides them, and such a station stops with a message saying so.
- A dropped connection is retried, waiting a bit longer each time, and after sleep the station connects again at once. When Windows reports the network back (or a new address, as when switching Wi-Fi), it connects right away instead of waiting, even if the retries ran out in the last 10 minutes.
- The "Add a station" page shows suggestions while the search box is empty: a hand-picked list (radio-browser `stationuuid`s in `Storage.RecommendedIds`) and the most popular stations of the system's country (`RegionInfo`, never the IP address), cleaned of spam and duplicates. They load once per run.
- Song titles come from the stream's ICY metadata; cover art from the iTunes Search API, used only when the artist matches.
- Windows media controls (Win+A, media keys, lock screen) are fed through `SystemMediaTransportControls`. A Start menu shortcut with the app's ID lets Windows and the Windhawk taskbar player know the app.
- Updates: every 6 hours the latest GitHub release is checked and downloaded in the background; a click on the green arrow renames the running exe to `*.old`, puts the new one in its place and restarts.

## Project structure

```
src/
  Program.cs     startup, single instance
  Radio/         tray icon, menu and playback (RadioApp), the panel (RadioPanel), dragging stations (StationDrag), station card (RadioOsd), README pictures (RadioShots, test build only)
  Audio/         station connection, decoding by Windows
  Services/      cover art, updates, storage, Windows integration, language
  Theme/         colours and Windows 11 style controls
  Assets/        app icon (radio.ico) and the Lucide icons' licence
docs/            icon.svg (the icon's source), download button, README screenshots
tools/IconMaker  draws radio.ico in all sizes: dotnet run --project tools/IconMaker -- <folder>
```
