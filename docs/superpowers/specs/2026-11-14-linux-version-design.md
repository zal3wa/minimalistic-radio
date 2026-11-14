# Minimalistic Radio for Linux: design

Date: 2026-11-14. Status: approved by the owner.

## Intent

People who use Linux ask for Minimalistic Radio. The owner wants the same app, used the same way, made for Linux and shaped by what Linux users expect. The owner doesn't know Linux, so the Linux-specific calls below are the assistant's, each with its reason. The Windows version (in `src/`) stays exactly as it is.

What the Windows app is today (version 2.2.4): a tray icon next to the clock. A right click opens a short menu, a left click opens a small panel with the station list, "now playing" with cover art, volume, a sleep timer and Play/Stop. It has pages for station search (radio-browser.info), song history and settings, a "station changed" card for media keys, Windows media controls, Polish and English. One small exe, no installer, no telemetry.

## Goals

- **The same app in use.** Every user-visible feature of Windows 2.2.4 has a Linux counterpart (see the feature map), except the few that exist only because of Windows.
- **It looks like Linux, not like Windows.** The window uses GNOME's own look (GTK 4 + libadwaita). Everything the desktop draws itself (tray menu, notifications, media controls, file dialogs) is native on every desktop automatically.
- **Installs the way Linux users install apps,** with one click and updated by the store: from **Flathub** (GNOME Software, KDE Discover, Mint's Software Manager) and from the **Snap Store** (Ubuntu's App Center). Ubuntu and Kubuntu don't support Flatpak out of the box, so without the Snap their users would need a terminal; the owner chose to ship both in 1.0.0.
- **Small and private**, in the spirit of the Windows version: no telemetry, no accounts, only the network connections the README lists.
- **Station lists move between systems:** a list exported on Windows imports on Linux and the other way round.

## Non-goals

- Changing the Windows app or its look.
- A KDE/Qt look, or a second UI per desktop.
- AppImage, .deb or other distro packages in the first version (Flathub and Snap only; others only if users ask).
- Checking GitHub for updates or replacing its own files (impossible in Flatpak, where the app's files are read-only, and GitHub would announce versions before Flathub has built them). Updates come from Flathub; see "Updates".
- An FFmpeg download, a "Decoding" setting or the Windhawk taskbar section. These exist only because of Windows.
- New features beyond what the Windows app does, apart from the small Linux adaptations listed below.
- Code signing. Flathub builds and serves the app, so Linux users get no SmartScreen-style warning.

## Anti-goals (failure even if it technically works)

- It feels like a Windows app on Linux: Windows 11 styling, a self-replacing binary, files in unusual places.
- Installing or running it needs a terminal.
- A Linux release breaks auto-updates of the Windows app (see Releases).
- It's heavy: a bundled runtime, Electron, or a download measured in tens of megabytes.

## Linux facts that shape the design

- **Windows can't be placed by the app.** Ubuntu, Fedora and KDE run on Wayland, where an app cannot choose where its window goes or keep a card pinned to the bottom of the screen. The panel opens where the desktop puts it, and the "station changed" card becomes a system notification.
- **The tray** is the StatusNotifierItem (SNI) standard over D-Bus, with the menu sent via `com.canonical.dbusmenu`. KDE Plasma, Cinnamon (Linux Mint), Xfce, Budgie and COSMIC show it. Ubuntu's GNOME shows it through the AppIndicator extension it ships enabled. Plain GNOME (Fedora, Debian) shows no tray at all.
- **GTK 4 has no tray API**, and there's no maintained GTK 4 Python library for it. The app implements SNI and dbusmenu itself on `Gio.DBus`, a few hundred lines. In Flatpak, a PID-based well-known bus name (`org.kde.StatusNotifierItem-PID-ID`) fails, so the item registers with the watcher by object path on the app's unique bus name. It needs the `--talk-name=org.kde.StatusNotifierWatcher` permission.
- **Media controls** are MPRIS (`org.mpris.MediaPlayer2.*`). Through it the media keys, GNOME's player under the clock, KDE's media widget and lock screens control the radio. This is the Linux equivalent of Windows' media controls and of the Windhawk taskbar player.
- **Running without a window, and autostart,** go through the Background portal (`org.freedesktop.portal.Background`). GNOME lists such apps under "Background Apps" in quick settings, where they can be quit.
- **Audio** is GStreamer `playbin`, from the GNOME Flatpak runtime. It plays MP3, AAC, Ogg/Opus, FLAC and HLS and reports ICY song titles as tags. Since Freedesktop SDK 25.08, AAC is decoded by `avdec_aac` from the auto-installed `codecs-extra` extension (fdk-aac was dropped), and there are reports of problems with it. **HE-AAC (AAC+) must be verified first** (see Risks).
- **Python and PyGObject are part of the GNOME runtime**, so a Python app adds almost nothing to the download.
- **App ID:** `io.github.zal3wa.MinimalisticRadio`. Flathub verifies `io.github.<user>` through the GitHub account.

## Approaches considered

How to build it:

1. **Python + GTK 4 + libadwaita + GStreamer, shipped as a Flatpak on Flathub. Chosen.** A common way to write GNOME apps. Everything it needs is in the GNOME runtime, so the app itself is tiny, and GStreamer plays every format with no FFmpeg download.
2. **C# + Avalonia.** The same language as the Windows app, with a built-in tray. Rejected: 40–70 MB per download, a Windows-like look, and little shareable code (almost everything in `src/` is Windows-specific).
3. **C# + GirCore (GTK 4 bindings for .NET).** A native look in C#. Rejected: young bindings, the .NET runtime in the Flatpak (70+ MB), and the same small amount of sharing.
4. **Rust + GTK 4** (like the Shortwave app). Native and fast. Rejected: slower to change, and nothing gained over Python for an app this size.
5. **Qt / KDE look**, or **Electron/Tauri.** Rejected: Qt looks foreign on Ubuntu and Fedora, and Electron/Tauri are heavy or add a third stack.

How it looks (decided by the owner): **GNOME style** (libadwaita), not KDE style and not a custom look. GNOME's building blocks map almost one to one onto the Windows 11 "settings cards" the Windows app already uses. Icons inside the window (play, stop, settings, history, add, sleep timer, copy) come from the **system icon theme** by their standard symbolic names, so they follow the user's theme (Adwaita, Breeze, Papirus…); the Windows app's Lucide icons are not used on Linux. Only the app icon and the tray icon are the radio's own (decided by the owner).

How the repository is organised (decided by the owner): **one repository** with separate releases per system (see Releases).

How it is shipped (decided by the owner): **Flathub and the Snap Store, both from 1.0.0.** The alternatives were Flathub only, where Ubuntu and Kubuntu users would have to enable Flatpak in a terminal, and Flathub first with the Snap later. Both would leave Ubuntu users, the largest group, with friction.

How updates work (decided by the owner): **the Windows-style green arrow, driven by Flathub through the Flatpak portal**, not by checking GitHub (see Updates).

## Feature map: Windows → Linux

| Windows 2.2.4 | Linux |
|---|---|
| Tray icon, tooltip "station: song" | SNI item: symbolic (monochrome) icon, tooltip with station and song |
| Left click: the panel next to the clock | SNI `Activate`: show/raise the panel window, placed by the desktop |
| Right click: menu | Native menu via dbusmenu, same items: Play/Stop · Station ▸ (stations, current one checked) · Volume (N%) ▸ Up 5%, Down 5%, Mute, 25, 50, 75, 100 % · Sleep timer ▸ 15/30/45/60/90 min, Off (checked) · station name (disabled) · song title · Settings · Quit, plus "Update" when one is ready (see "Updates"). *Assistant's call:* clicking the song title opens the panel and copies the title there, with a "Copied" toast, because on Wayland an app can only set the clipboard while it has focus, and a tray menu click leaves the focus with the desktop |
| None | *Linux adaptation:* scrolling on the tray icon changes the volume (SNI `Scroll`), because Linux tray users expect it |
| Panel: header (+ Station, history, settings, close), station list with logos and a ⋯ menu (Edit, Move up, Move down, Remove), "Now playing" card with cover and copy button, volume slider with a moon button for the sleep timer, Play/Stop | `AdwApplicationWindow` with an `AdwNavigationView`. Same layout: header bar with the same buttons, a boxed list of stations (logo, name, playing mark, menu button), the now-playing card, the volume `GtkScale` with a sleep-timer button, and a "pill" Play/Stop button. Closing the window only hides it |
| Add a station page: search, results with logo, country · codec bitrate · tags, + or ✓, "Add by address" | Same page in the navigation view. "Add by address" and "Edit" open an `AdwDialog` with name, stream address, optional logo address |
| History page: song, station · time, ⋯ (Copy, Search on Spotify, Search on YouTube), Clear history; 100 entries, consecutive repeats skipped | Same |
| Settings: Language; Start with Windows; Show station changes; Decoding/FFmpeg; Station list Export…/Import…; Taskbar/Windhawk; About; Updates; Quit | Settings page in GNOME preferences style: **Language** (Same as system / Polski / English); **Start with the system** (Background portal: starts hidden, doesn't play by itself, like Windows); **Show station changes** (notification); **Station list** Export…/Import… (file chooser portal); **About** (opens `AdwAboutDialog`: version, MIT, Lucide icons, GitHub link); **Quit**. Decoding, Taskbar and Updates are dropped |
| Station change card at the bottom of the screen (media key or menu switch) | A system notification with the cover art, station name and song, replacing the previous one. Same on/off setting |
| Windows media controls (Win+A, media keys, lock screen); Next/Previous switch stations | MPRIS: Play, Pause, PlayPause, Stop; Next/Previous switch stations; metadata (song or station as title, station, cover via `mpris:artUrl`), Volume, CanGoNext/Previous |
| Green update arrow in the header, "Update to X" in the tray menu, Settings → Updates (on/off, Check now); checks GitHub every 6 h and replaces the exe | The same green arrow and an "Update" tray menu item, driven by the Flatpak portal's update monitor (see "Updates"). No Updates settings card: the store manages updates |
| Balloon tips (copy failed, updated) | `AdwToast` in the window. Nothing for "updated" |
| Auto-reconnect: 2, 3, 5, 10, 15, 30 s; up to 10 attempts once it has played, 2 before; counter resets after a minute of playing; status "Connection lost. Retrying in N s…" | Same |
| Sleep timer stops playback | Same |
| Covers from the iTunes Search API, used only when the artist matches | Same, cached in the app's cache folder |
| Radio 357 song titles from `stream.radio357.pl/now/playing.json` | Same |
| Single instance; starting it again opens the panel | `Gtk.Application` uniqueness: a second launch opens the panel |
| Polish or English, following Windows | Same, following the system's preferred languages, through gettext (see "Linux expectations") |
| Light/dark following Windows | libadwaita follows the system automatically, accent colour included |
| `%LOCALAPPDATA%\Minimalistic Radio`: `stations.json`, `preferences.json`, `history.json` | The app's XDG config/data folders (inside the Flatpak's own folder). Same file names and JSON shapes: `[{"Name","Url","Logo"}]` for stations, so export/import are interchangeable with Windows |
| Start menu shortcut, Run key | Desktop file and AppStream metadata installed by Flatpak; autostart through the portal |

**When there's no tray** (plain GNOME): the app checks for `org.kde.StatusNotifierWatcher` with a registered host. Without one, it is an ordinary window app. Closing the window keeps the radio playing in the background, the controls stay under the clock (MPRIS), and the app list or GNOME's "Background Apps" reopen or quit it. The first time the window is closed this way, a notification says the radio keeps playing and where to find it. *(Assistant's call: otherwise users would think it crashed or quit.)*

**Keyboard** *(assistant's call: standard for GNOME apps)*: Escape closes the panel, Enter searches, Ctrl+W closes the window, Ctrl+Q quits.

## Linux expectations (chosen by the owner)

Small things Linux users notice, built in from the start:

- **Name and icon in the volume mixer.** The audio stream carries the app's name and icon (`GLib.set_application_name`, plus `application.name`, `application.icon_name` = the app ID and `media.role` = `music` on the PipeWire/PulseAudio stream), so mixers show "Minimalistic Radio" and not "python3".
- **No idle suspend while playing.** GNOME can suspend an idle laptop even while music plays, which Windows doesn't. While the radio plays, the app holds a suspend inhibitor (`Gtk.Application.inhibit` with `SUSPEND`, which goes through the Inhibit portal in a sandbox). Stopping or the sleep timer releases it.
- **Back after sleep and network changes.** After resume (logind `PrepareForSleep(false)`) or when the network comes back (`Gio.NetworkMonitor`), the app reconnects. This happens if it was playing, or if it gave up retrying because the connection was lost less than 10 minutes earlier (not hours later somewhere else). Windows 2.3.0 gets the same network rule.
- **Translations in the Linux format.** English strings in the code, gettext `.po` files (Polish first) with Meson's i18n, and the desktop file and AppStream metadata translated too. Anyone can then add a language; a hosted translation service (Weblate) can come later. The Polish texts reuse the Windows app's.

Free with MPRIS, nothing to build: control from a phone (KDE Connect, GSConnect), desktop media shortcuts, `playerctl`.

Not now: a GNOME Shell search provider and desktop widgets.

## Updates

Decided with the owner: the Windows experience (a green arrow, one click updates and restarts) stays, but the Linux way, through Flathub instead of GitHub.

- Most distributions already update Flatpak apps in the background (GNOME Software, Linux Mint's Update Manager). The app adds the familiar arrow on top of that.
- The app creates an update monitor through the Flatpak portal (`org.freedesktop.portal.Flatpak.CreateUpdateMonitor`, portal version 2 or later). On `UpdateAvailable`:
  - if the newer version is only on the remote, the arrow and the tray item say "Update". A click calls the monitor's `Update`, and when it finishes the app restarts itself (`Spawn` through the portal, then quits), playing the same station if it was playing.
  - if the newer version is already installed (the store updated it in the background), they say "Restart to update", and a click only restarts.
- The portal gives no version number, so the labels carry none.
- No settings card and no network request of the app's own for updates. The user can block self-updates with Flatpak permissions; then the arrow never shows.
- Outside Flatpak (the Snap, developer runs) or without portal version 2, no arrow. In the Snap, snapd refreshes the app automatically and itself tells the user when to close the app to finish an update.

## Repository, builds and releases

- **Layout:** `src/` stays untouched (Windows). The Linux app lives in `linux/`: the Python package, data files (desktop file, AppStream metainfo, icons including a symbolic tray icon), tests, a Meson build (the usual way to install GNOME Python apps) and the Flatpak manifest. The app icon comes from `docs/icon.svg`.
- **Versions and tags:** Linux has its own version, starting at **1.0.0**, with tags **`linux-vX.Y.Z`**. Windows keeps `vX.Y.Z`; the existing workflow's `v*` tag filter doesn't match `linux-v…`.
- **Must not break Windows updates:** the Windows updater reads GitHub's `releases/latest`, and the README's download button uses `releases/latest/download/Minimalistic-Radio.exe`. Linux releases are therefore created with **`--latest=false`**, so "latest" always stays a Windows release.
- **CI:** a new `.github/workflows/linux.yml` on `ubuntu-latest` runs the tests and builds the Flatpak for changes under `linux/`. On a `linux-v*` tag it publishes a GitHub release (not marked latest) with a `.flatpak` bundle and release notes from the annotated tag, like Windows. The Windows workflow gets a path filter so Linux-only changes don't rebuild the exe; this is the only change to Windows files besides the README.
- **Snap:** a `snapcraft.yaml` in `linux/`: strict confinement, base `core24` with the `gnome` extension (GTK 4, libadwaita, GStreamer from the GNOME content snap), snap name `minimalistic-radio`. Plugs at least `network`, `audio-playback`, `desktop`, `desktop-legacy`, `wayland`, `x11`; an `mpris` slot for media controls. File dialogs go through the portal, so no `home` access. Before relying on them, verify inside the Snap: the SNI tray, AAC/HE-AAC decoding (stage `gst-libav` if the content snap lacks it), and autostart. If the Background portal doesn't work for snaps, use snapd's own `autostart` desktop-file mechanism. The `linux.yml` workflow builds the Snap and, on a `linux-v*` tag, publishes it to the Snap Store's `stable` channel; pre-releases go to `beta`.
- **Flathub:** after the first release, the app is submitted to Flathub. Flathub then creates its own repository (`flathub/io.github.zal3wa.MinimalisticRadio`) holding only the manifest that points at this repository's tag. Until it is accepted, the `.flatpak` bundle from GitHub can be opened with GNOME Software or KDE Discover.
- **What only the owner can do** (the builder prepares everything and gives step-by-step instructions): create a Snap Store (Ubuntu One) account, register the name `minimalistic-radio`, and store the publishing credentials as the GitHub secret `SNAPCRAFT_STORE_CREDENTIALS`; open the Flathub submission pull request from the owner's GitHub account and answer the reviewers.
- **README** (layout decided by the owner): at the top, a "Download for Linux" button next to "Download for Windows", drawn in the same style, linking to a Linux section. That section has the official Flathub and Snap Store badges (each shown once it is live), screenshots in light and dark produced by a screenshot mode like Windows' `--screenshot`, and the Privacy and Uninstall notes for Linux. The tray menu is drawn by the desktop, so its screenshot comes from a real Linux desktop (a beta tester), not from the screenshot mode. The Linux button appears with the first Linux release.

## Privacy

The same list as Windows, minus GitHub update checks and the FFmpeg download: station servers, station logo hosts, radio-browser.info (search), itunes.apple.com (artist and title for covers), stream.radio357.pl (only while Radio 357 plays). Update checks are made by Flatpak against Flathub, not by the app.

## Testing

- **Unit tests** (pytest) for the logic that doesn't need a desktop: ICY title clean-up, duplicate-stream detection (the same rules as `Storage.StreamKey` on Windows), radio-browser result parsing, cover matching, history rules, reconnect timing, the sleep timer, and reading and writing Windows-format JSON files.
- **Self-test mode** (like Windows' `--test-menu`): builds every page, the tray menu layout and the MPRIS object, then exits with 0. In CI it runs headless under `dbus-run-session` with a fake SNI watcher, so tray registration and menu layout are checked over real D-Bus.
- **Playback test:** a tiny local HTTP server sends MP3, AAC, HE-AAC and Opus test streams with ICY metadata. The test checks that sound starts and titles arrive. It runs inside the Flatpak runtime and inside the Snap too, because that's where AAC decoding is in question.
- **By hand, before 1.0.0:** a checklist for Ubuntu with the Snap (GNOME with AppIndicator), Fedora with the Flatpak (GNOME without tray), Fedora KDE or Kubuntu with the Flatpak, and Linux Mint (Cinnamon) with the Flatpak. The owner works on Windows 11 Home, where WSL can show the window but not a tray or media controls. So the first testers are **the Linux users who asked for the app**, with the checklist: on Ubuntu from the Snap Store's `beta` channel, elsewhere with the `.flatpak` from a pre-release.

## Risks

1. **HE-AAC in the Flatpak runtime and the Snap.** Many stations, Polish ones among them (e.g. Polskie Radio "AAC+"), send HE-AAC. If `avdec_aac` in `codecs-extra` (or the Snap's GStreamer) plays it wrongly (mono, muffled, silent), the app fails for those stations. **This is checked first, before building the UI**, with real AAC+ stations inside both. If it fails, stop and bring the options to the owner.
2. **No tray on plain GNOME.** Handled by the window mode above.
3. **KDE Plasma 6.7 "Background Apps"** can show a Flatpak app running without a window a second time in the tray (an upstream KDE bug from June 2026). Check it during the KDE test; if it happens, mention it in the README and follow the KDE fix.
4. **Testing without Linux at hand:** covered by CI plus beta testers. The owner may need guidance on the beta.
5. **Two sandboxes.** The tray, media controls, autostart and audio can behave differently in Snap and Flatpak, so each is checked in both.

## Left to the builder

- The current stable GNOME runtime version at build time.
- HTTP: Python's standard library in worker threads, or libsoup 3 through GObject introspection. Prefer no pip dependencies.
- Exact widget composition, sizes and spacing, within GNOME's design guidelines.
- The symbolic tray icon's drawing, based on the app icon.
- Module layout inside `linux/` and the Meson details.
- The exact strings, reusing the Windows app's Polish and English texts wherever they still fit.
