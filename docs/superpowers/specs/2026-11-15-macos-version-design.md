# Minimalistic Radio for macOS: design

Date: 2026-11-15. Status: approved by the owner.

## Intent

The owner uses a Mac and wants the radio there too. It's the same app, used the same way as on Windows, built the way Mac apps are built and using what macOS offers where that makes it more useful for Mac users. The Windows app (`src/`) and the Linux app (`linux/`) stay as they are. The owner doesn't develop for the Mac, so the Mac-specific calls below are the assistant's, each with its reason. Development happens on the owner's Windows PC. GitHub's macOS runners build and test the app (free for this public repository), and the owner tests it on their own Mac.

What the Windows app is today (version 2.5.0):

- **Tray icon next to the clock.** A right click opens a short menu: Play/Stop, Station ▸, Volume (N%) ▸, Sleep timer ▸, the station and its song (a click copies the song), Settings, Quit, and Update when one is ready. A left click opens a small panel.
- **The panel:**
  - a header with + Station, History, Settings and Close;
  - the station list with logos, reordered by dragging (holding a station for 250 ms lifts it), with a ⋯ menu for Edit and Remove;
  - a "Now playing" card with the cover and a copy button that confirms the copy;
  - a Windows 11-style volume row: a speaker icon that mutes on click, a slider with a live value bubble, and a moon button for the sleep timer;
  - a Play/Stop button.
- **Pages:**
  - **Add a station:** search of radio-browser.info, with suggestions when the box is empty: Recommended (hand-picked music stations), Popular in your country (the country comes from the radio's language), and Popular worldwide. "Add by address" adds a station from its stream address.
  - **Song history:** 100 entries, with Copy, Search on Spotify and Search on YouTube, and Clear history.
  - **Settings:** Language (system or one of nine), Start with Windows, Show station changes, Station list Export…/Import…, Updates (on/off, Check now), About and Quit.
- **System integration:**
  - a "station changed" card at the bottom of the screen after a media key or menu switch;
  - Windows media controls, where Next and Previous switch stations;
  - self-updates from GitHub, shown as a green arrow;
  - reconnecting after a dropped connection, sleep or a network change.
- **Data:**
  - stations in `data/banned-stations.json` are never shown;
  - Radio 357 song titles come from its own feed;
  - covers come from the iTunes Search API.
- **Size and privacy:** one 219 KB exe, no installer, no telemetry.

## Goals

- **The same app in use.** Every user-visible feature of Windows 2.5.0 has a Mac counterpart (see the feature map).
- **It is a Mac app:**
  - a menu bar item with no Dock icon;
  - SF Symbols, system materials, dark mode and the accent colour;
  - the standard shortcuts;
  - "Now Playing" in Control Center, the media keys and AirPods.
- **Mac extras, chosen by the owner:** AirPlay, and Shortcuts with Siri.
- **Free.** No Apple Developer Program. The app is a download from GitHub Releases.
- **Small and private.** A few megabytes at most for a universal build, no bundled runtime. It connects only to the servers the README lists.
- **Station lists move between all three systems.** It uses the same `stations.json` format as Windows and Linux, so Export and Import are interchangeable.
- **Updates like Windows:** a green arrow, one click, and the radio updates and restarts itself.

## Non-goals

- **Anything that needs the paid Apple Developer Program:** the Mac App Store, notarization, a Homebrew cask (Homebrew removes casks that fail Gatekeeper; the cutoff was 1 September 2026), and iCloud sync of the station list.
- **A desktop or Notification Center widget.** The owner wants it later.
- Changes to the Windows or Linux apps.
- iPhone and iPad.
- **Formats beyond what AVFoundation plays (Ogg/Opus, FLAC).** Windows doesn't play them either.
- **New features beyond Windows 2.5.0,** apart from the Mac adaptations and the two extras below.

## Anti-goals (failure even if it technically works)

- **It feels like a Windows app on the Mac:** Windows 11 styling, the Lucide icons inside the window, a Dock icon, its own window frame.
- **It's heavy:** Electron, a bundled Python, a download over about 10 MB.
- **Every update brings permission prompts again,** or the user has to repeat the Gatekeeper steps.
- **A Mac release breaks the Windows auto-update.** Mac releases are never marked "latest".
- **Installing it needs a terminal.**

## macOS facts that shape the design

- **Unsigned apps and Gatekeeper.** Since macOS 15, an app that isn't notarized can't be opened with Control-click → Open. The first launch is blocked, and the user opens System Settings → Privacy & Security → "Open Anyway" and confirms with their password. This is needed once per installation. Files the app downloads itself (URLSession) don't get the quarantine flag, so self-updates don't repeat it.
- **A stable code identity, for free.** An ad-hoc signature has no stable designated requirement, so macOS treats every new version as different code and asks again for permissions. *Assistant's call:* every build is signed with the project's own **self-signed code-signing certificate**. Its private key is a GitHub secret, and the owner keeps a backup in a password manager, as with the Flatpak key. Versions then share one identity. This doesn't remove the first-launch Gatekeeper step. Apple Silicon needs some signature to run code at all, and this covers it.
- **The menu bar item.** SwiftUI's `MenuBarExtra` can't tell a left click from a right click. The status item is therefore an AppKit `NSStatusItem`, and the panel and the card are borderless `NSPanel`s with SwiftUI content. Unlike on Wayland, the app places its own windows: the panel opens right under the menu bar icon.
- **No Dock icon:** `LSUIElement`. Such an app has no menu bar menus of its own, so Settings stays inside the panel, as on Windows.
- **Now Playing:**
  - `MPNowPlayingInfoCenter` and `MPRemoteCommandCenter` give Control Center's Now Playing module, the media keys, AirPods controls and the Touch Bar.
  - On macOS the app must set `playbackState` itself.
- **Audio:**
  - `AVPlayer` plays MP3, AAC and HE-AAC over HTTP(S) (Icecast, Shoutcast), and HLS.
  - Song titles (ICY `StreamTitle`) arrive as timed metadata (`AVPlayerItemMetadataOutput`). This must be checked with real stations early (see Risks).
  - AVFoundation doesn't play Ogg.
- **Sleep.** macOS keeps the Mac from idle sleep while audio plays (coreaudiod), so the app adds nothing. Linux needed an inhibitor.
- **Wake and network changes:** `NSWorkspace.didWakeNotification` and `NWPathMonitor`.
- **Open at login:** `SMAppService.mainApp` (macOS 13+). The radio appears in System Settings → General → Login Items, where the user can also turn it off. The app reads the current state from there.
- **AirPlay:** `AVRoutePickerView` bound to the player (macOS 10.15+).
- **Shortcuts and Siri: App Intents** (macOS 13+).
  - The intents and an `AppShortcutsProvider` appear in the Shortcuts app and in Spotlight (macOS 26 runs app actions from Spotlight), and can be spoken to Siri.
  - App Intents metadata is produced by the Xcode build, so the app is an Xcode project.
  - Siri isn't available in Polish. Shortcuts and Spotlight work in every language, and Siri phrases exist in the languages Siri supports.
- **A second launch** of an `LSUIElement` app reaches `applicationShouldHandleReopen`, which opens the panel (the Windows single-instance behaviour).
- **The clipboard** (`NSPasteboard`) has no focus restriction, so copying the song from the menu works directly, unlike on Wayland.
- **Where files go:** `~/Library/Application Support/Minimalistic Radio/` holds `stations.json`, `preferences.json` and `history.json` (same names and JSON shapes as Windows). Logos and covers go in `~/Library/Caches/io.github.zal3wa.minimalistic-radio/`.
- **Bundle ID:** `io.github.zal3wa.minimalistic-radio`, the same as the Linux app ID.
- **Supported Macs:** macOS 13 Ventura or newer (for SMAppService, App Intents and a mature SwiftUI), as a universal binary for Apple Silicon and Intel.

## Approaches considered

How to build it:

1. **Swift, with SwiftUI for the content and AppKit for the status item and its panels; AVFoundation, MediaPlayer, App Intents, ServiceManagement. Chosen.** It's the only way to get Shortcuts and Siri and the native AirPlay picker. The frameworks and the Swift runtime are part of macOS, so the app stays small, and it looks like macOS without effort.
2. **The Linux app's Python code, with PyObjC and py2app.** Rejected: the bundle carries Python (tens of MB), App Intents can't be written in Python (they need Swift's compile-time metadata), and the result is less native.
3. **C# (Avalonia or .NET MAUI) or Electron/Tauri.** Rejected: heavy, not a Mac look, no App Intents. Almost nothing in the WPF app could be shared anyway.

Distribution (decided by the owner): **free, without the Apple Developer Program.** A DMG on GitHub Releases, the self-signed identity above, and "Open Anyway" once.

Extras (decided by the owner): **AirPlay, and Shortcuts with Siri.** The widget comes later.

## Feature map: Windows 2.5.0 → macOS

| Windows 2.5.0 | macOS |
|---|---|
| Tray icon, tooltip "station: song" | Menu bar item: the radio's own icon as a template image (monochrome, follows the menu bar's light/dark look), tooltip with station and song |
| Left click: the panel | Click: the panel, a borderless `NSPanel` right under the icon with the system's window material and rounded corners. It closes on a click elsewhere or on Esc. A second click on the icon closes it |
| Right click: the menu | Right click or Control-click: an `NSMenu` with the same items: Play/Stop · Station ▸ (current one checked) · Volume (N%) ▸ Up 5%, Down 5%, Mute, 25, 50, 75, 100 % · Sleep timer ▸ 15/30/45/60/90 min, Off (checked) · station name (disabled) · song title · Update (when ready) · Settings… · Quit. A click on the song copies it, and the card shows "Copied" *(assistant's call: a menu closes on click, so the feedback goes to the card)* |
| Panel header: + Station, History, Settings, Close | Same, with SF Symbols (`plus`, `clock.arrow.circlepath`, `gearshape`, `xmark`), plus the green update arrow when one is ready |
| Station list with logos, playing mark, ⋯ menu (Edit, Remove), drag to reorder | Same list. Reordering is the Mac list's own drag: the row follows the pointer and a line shows where it will land. *Assistant's call:* Mac lists drag at once, so there's no 250 ms hold, but it keeps what the Windows work aimed for: logos don't reload on drop, and the playing station stays marked. Arrow keys with ⌘⌥ move the selected station *(Windows has keyboard moving too)* |
| "Now playing" card with cover and copy button, "Copied" feedback | Same. The copy button turns into a checkmark with "Copied" for about 1.5 s |
| Volume row: speaker (click mutes), slider with live value, moon (sleep timer) | Same row with SF Symbols (`speaker.slash`, `speaker.wave.1…3`), the value shown while dragging, the moon for the sleep timer, and the **AirPlay** button (Mac extra) |
| Play/Stop button | A large prominent button, as wide as the panel |
| Add a station: search, results (logo, "country · codec bitrate · tags", + or ✓), suggestions (Recommended, Popular in your country, Popular worldwide), "Add by address" | Same page, same rules: the same Recommended UUIDs, the country from the radio's language (`docs/superpowers/specs/2026-11-15-languages-and-country-design.md`), the banned list from `data/banned-stations.json`, and the spam filter. The playable filter: MP3, AAC, AAC+, unknown codecs, and **HLS** (the Mac plays it, Windows doesn't). "Add by address" and Edit open a sheet with name, stream address and an optional logo address |
| History: 100 entries, consecutive repeats skipped, ⋯ Copy, Search on Spotify, Search on YouTube, Clear history | Same |
| Settings: Language; Start with Windows; Show station changes; Station list Export…/Import…; Updates (on/off, Check now); About; Quit | Settings page in macOS style (grouped form): **Language** (Same as system + nine); **Open at login** (SMAppService); **Show station changes**; **Station list** Export…/Import… (`NSSavePanel`/`NSOpenPanel`); **Updates** (on/off, Check now, as on Windows: the app updates itself); **About** (version, MIT, link to GitHub); **Quit** |
| Station change card at the bottom of the screen | A small card under the menu bar icon, in the system's HUD material, with logo or cover, station and song, for about 3 s, after a media key, menu or Shortcuts switch. Same on/off setting |
| Windows media controls; Next/Previous switch stations | Now Playing: Control Center, media keys, AirPods, Touch Bar; Next/Previous switch stations; song as title, station as artist, cover as artwork |
| Update arrow, "Update" in the menu, checks every 6 h, replaces the exe | Same idea, Mac mechanics (see Updates) |
| Balloon tips (copy failed, updated) | The card, or a line in the panel |
| Reconnecting: 2, 3, 5, 10, 15, 30 s; up to 10 tries once it has played, 2 before; counter reset after a minute of playing; "Connection lost. Retrying in N s…" | Same, plus reconnecting after wake or when the network comes back, with the Linux rule (if it was playing, or gave up less than 10 minutes earlier) |
| Sleep timer | Same |
| Covers from iTunes, only when the artist matches | Same |
| Radio 357 titles from `stream.radio357.pl/now/playing.json`; iHeart title format | Same |
| Single instance; starting again opens the panel | `applicationShouldHandleReopen` opens the panel |
| Nine languages; the system's or the chosen one | Same nine. The texts are converted from the Windows `.po` catalogues into the Mac's String Catalog. "Same as system" follows macOS's preferred languages, including the per-app language in System Settings. Choosing a language in Settings switches the UI at once, as on Windows |
| Light/dark | Automatic, with the accent colour |
| `%LOCALAPPDATA%\Minimalistic Radio` | `~/Library/Application Support/Minimalistic Radio/` (same files) |
| Start menu shortcut (name and icon in the media controls) | Not needed: the app is in /Applications and Now Playing shows its name and icon |

**Keyboard** *(assistant's call: Mac standards)*: Esc closes the panel or goes back a page, ⌘, opens Settings, ⌘F opens search, ⌘W closes the panel, ⌘Q quits, Space plays/stops while the panel has focus.

## Mac extras (chosen by the owner)

**AirPlay.** A route picker button in the volume row. The radio then plays on HomePods, Apple TVs and AirPlay speakers. Live streams over AirPlay lag by a couple of seconds, which doesn't matter for radio.

**Shortcuts and Siri (App Intents):**

- **Actions:**
  - Play (the last station, or a chosen one);
  - Play station (the user's stations, offered by name);
  - Stop;
  - Next station and Previous station;
  - Set sleep timer (minutes, or off);
  - Set volume (0–100).
- **App Shortcuts** with ready-made phrases, for example "Play Antyradio Hard in Minimalistic Radio" and "Stop Minimalistic Radio". They appear in Spotlight and in the Shortcuts app without any setup, and run from Siri in the languages Siri supports.
- **What users can build with them:** automations such as "at 7:00 play this station", a keyboard shortcut for an action, a control in Control Center through Shortcuts.
- **When the panel is closed:** actions run without opening it. A station switch shows the card, as a media key does.

## Updates

As on Windows, but for a `.app` bundle:

- **Checking:** every 6 hours (Settings → Updates on), and on "Check now". The app reads the repository's releases from the GitHub API and takes the newest one whose tag starts with `macos-v`. Mac releases are never "latest", so it can't use the latest-release endpoint. A beta build also takes betas; a full release takes only full releases.
- **Download:** the release has a zip of the app for the updater and a DMG for people. When the user clicks the arrow (or "Update" in the menu), the app downloads the zip and unpacks it to a temporary folder. It then checks that the new app's code signature meets the running app's designated requirement, which proves the same self-signed certificate. It swaps the bundle in place and restarts, playing the same station if it was playing.
- **If macOS asks once** (an App Management permission, or an administrator password for /Applications), that's acceptable: every version shares the self-signed identity, so the grant is expected to last. The app explains the prompt in a line before it appears. *(Assistant's call: the anti-goal is a prompt on every update, not a single one.)*
- **If the swap is refused anyway**, the decision is made on that Mac while the app runs, not once for everyone. The app opens the downloaded DMG in Finder and asks the user to drag the radio to Applications, and from then on the arrow on that Mac says "Download update". A downloaded update is never silently dropped. *(Assistant's call: one Mac's refusal shouldn't take silent updates from everyone else.)*

## README download button

`releases/latest/download/...` always means the Windows exe, because Mac releases are never "latest". *Assistant's call:* the Mac release workflow also uploads the DMG to one fixed pre-release with the tag `macos-download`, replacing its file each time. The button can then always point to `https://github.com/zal3wa/minimalistic-radio/releases/download/macos-download/Minimalistic-Radio.dmg`. It stays on github.com, which people trust. The updater ignores that release, because its tag doesn't start with `macos-v`.

The README gets:

- a third download button, "Download for macOS";
- a macOS section laid out like the Windows and Linux ones: one wide menu bar picture, then the panel, search, history and settings in a 2×2 grid;
- the "Open Anyway" steps;
- macOS lines in Privacy and Uninstall.

## Repository, builds and releases

- **Code:** the Mac app lives in `macos/`, as an Xcode project. The Windows and Linux code don't change.
  - `data/banned-stations.json` is used directly from the repository root (Xcode can include it), so there's no third copy.
  - The Recommended UUIDs are a list in code, as on Windows and Linux; a change to the list changes all three.
- **CI:** `.github/workflows/macos.yml` runs on a macOS runner.
  - Every push that touches `macos/`: it builds the universal app, runs the unit tests and uploads the DMG as an artifact.
  - On `macos-v*` tags it also signs with the self-signed certificate (secrets `MACOS_SIGNING_CERTIFICATE`, a base64 .p12, and `MACOS_SIGNING_PASSWORD`), builds the DMG (`hdiutil`) and the updater zip (`ditto`), and creates the release with `--latest=false`, as a pre-release for `-beta.N`. Then it updates the `macos-download` release.
  - `build.yml` (Windows) and `linux.yml` ignore `macos/**`; `macos.yml` ignores everything else except `data/banned-stations.json`.
- **Tags:** `macos-vX.Y.Z`, betas `macos-vX.Y.Z-beta.N`. The version lives in one place in the project, and the release job stops if it differs from the tag (as in Linux).
- **Testing on the owner's Mac:** beta releases, as with Linux. The first one is used to check the risks below.
- **Screenshots:**
  - The app has a test-only screenshot mode, as on Windows and Linux. It renders the panel pages at 2× in light and dark with the same stations, songs and cover as the other systems. CI runs it.
  - The menu bar picture is either drawn around the real menu (as on Windows) or taken on the owner's Mac. The builder decides after trying CI.

## Privacy

The same servers as Windows: the stations, the logo sites, radio-browser.info, itunes.apple.com, api.github.com (update checks, can be turned off), github.com (downloads), and stream.radio357.pl. AirPlay stays on the local network. When Siri is used, Apple processes the spoken request, as for any app, and the README says so.

## Testing

- **Unit tests in CI** for the logic:
  - parsing titles, including Radio 357 and iHeart;
  - the directory: parsing, playable filter, bans, spam, country;
  - covers matching;
  - storage: reading Windows and Linux `stations.json`, `preferences.json` and `history.json`;
  - comparing update versions.
- **A smoke run in CI:** the app starts in a test mode, builds its menu and pages, and quits with code 0.
- **The owner's checks:** a short checklist (`docs/MACOS-TEST-CHECKLIST.md`) like the Linux one.
- **The first beta checks the risks** below on the owner's Mac before the rest of the work depends on them.

## Risks

The owner's Mac, where they're checked: an Apple M1, an administrator account, a recent macOS (the exact version is noted when the checks start). So the beta tests the administrator path of the self-update. The README pictures are rendered on GitHub's newest macOS runner image, so they show the current Mac look. A standard account is covered by the DMG fallback but not tested by hand.

To be checked first, on the owner's Mac, with a small beta:

1. **Self-update without the paid program.** macOS 13+ guards app bundles ("App Management"), and a standard user can't write to /Applications. The swap may ask once for permission or a password, which is acceptable, or be refused, which switches that Mac to the DMG path (see Updates). The beta checks two updates in a row: the first shows what macOS asks, the second shows that a grant lasts.
2. **Song titles from AVPlayer.** Some servers' ICY titles may not arrive through AVPlayer's metadata (test KIIS/iHeart, Antyradio, Radio 357, RMF). The fallback keeps AVPlayer as the player, because HLS, AirPlay and Now Playing all depend on it. The app opens the stream itself (URLSession), reads the titles out of the ICY metadata, and passes the audio on to AVPlayer through `AVAssetResourceLoader`. That's still one connection per station, and nothing to bundle. It applies to plain Icecast/Shoutcast streams only. HLS keeps AVPlayer's own metadata. *(Assistant's call: a separate player of the app's own would lose HLS and the AirPlay button, and a second title-only connection would double the traffic and count the listener twice.)*
3. **App Intents in a self-signed app.** If Shortcuts or Spotlight don't list the actions of a non-notarized app, the fallback is a URL scheme (`minimalistic-radio://play?station=…`). Shortcuts can open it, but Siri phrases are then lost.
4. **Open at login for a self-signed app** (SMAppService). If it's refused, the fallback is a short "add it in System Settings → Login Items" instruction with a button that opens that page.
5. **The Gatekeeper path itself.** Apple may make unsigned apps harder to run in a future macOS. Then the paid program would be the only way, and that is the owner's decision.

Other risks:

- **Siri doesn't speak Polish.** Shortcuts and Spotlight still work in Polish.
- **The owner tests on one Mac.** Intel Macs are built for but not tested by hand.

## Left to the builder

- How the Xcode project is kept: committed `.xcodeproj` or generated from a spec (XcodeGen).
- Code structure, test framework, and exact spacing and symbol choices within the Mac look described above.
- How the menu bar screenshot is made.
- The order of the work. The risk checks go first.
