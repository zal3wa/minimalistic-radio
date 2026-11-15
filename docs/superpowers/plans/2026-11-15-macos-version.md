# Minimalistic Radio for macOS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A native macOS version of Minimalistic Radio: a menu bar app with the same features as Windows 2.5.0, plus AirPlay and Shortcuts/Siri. It's free (self-signed, a DMG on GitHub Releases) and updates itself.

**Architecture:**
- **`RadioCore`:** a Swift package with no AppKit. It's a line-by-line port of the Linux app's tested logic (`linux/minimalistic_radio/core/*`, `controller.py`, `platform/menu_model.py`), plus Mac-only pure logic: updates, panel geometry and error classification. Its tests are ports of the Linux unit tests.
- **The app target:** AppKit for the status item, panels and menu, SwiftUI for the panel pages. AVFoundation plays, MediaPlayer gives Now Playing, App Intents give Shortcuts and Siri, ServiceManagement opens it at login.
- **Build and test:** everything is built and tested on GitHub's macOS runners. The development machine is Windows, so there's no local Xcode.

**Tech Stack:** Swift (language mode 5), SwiftUI + AppKit, AVFoundation, MediaPlayer, AppIntents, ServiceManagement, Network, Security; Swift Testing; XcodeGen; GitHub Actions (`macos-26` runner image, or `macos-15` if 26 isn't offered); `hdiutil`, `ditto`, `codesign`, `gh`.

**Spec:** `docs/superpowers/specs/2026-11-15-macos-version-design.md`. Read it first, because the feature map there is the source of truth for the UI.

## How to work on this plan

- **Where:** branch `macos`. Push it after each task. Merging into `main`, tags and releases happen only with the owner's explicit OK.
- **How to verify:** there's no Xcode here, so each verification step is `git push origin macos`, then `gh run watch <id> --exit-status` on the run of `.github/workflows/macos.yml` for that commit. "PASS" means that job is green. Read the failed step's log with `gh run view <id> --log-failed`.
- **Ported logic:** the Linux file named in each task is the reference. Port its behaviour exactly, including the constants and messages. When a step says "port every case of `linux/tests/unit/test_x.py`", each Python test becomes a Swift `@Test` with the same name in lowerCamelCase and the same inputs and assertions.
- **Commits:** every commit message ends with:

  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01MDL5yuTCFPxhSC7ke6mykg
  ```

## Global Constraints

- **Identity:**
  - Bundle ID `io.github.zal3wa.minimalistic-radio`; app and executable name `Minimalistic Radio`.
  - macOS 13.0 deployment target, universal (`arm64 x86_64`).
  - The version lives in `macos/project.yml` (`MARKETING_VERSION`), starting at `1.0.0`.
- **Build settings:**
  - Swift language mode 5, `SWIFT_STRICT_CONCURRENCY: minimal`. No third-party packages (no Sparkle).
  - Info.plist: `LSUIElement` YES, `NSAppTransportSecurity` → `NSAllowsArbitraryLoads` YES (radio streams and logos are often plain http), `MRReleaseTag` = `$(MR_RELEASE_TAG)`, which is `dev` unless CI sets the tag.
  - No App Sandbox, no hardened runtime, not notarized.
- **Data:**
  - `~/Library/Application Support/Minimalistic Radio/` holds `stations.json`, `preferences.json` and `history.json`.
  - Caches go in `~/Library/Caches/io.github.zal3wa.minimalistic-radio/` under `logos/` and `covers/`.
  - `stations.json` has the shape `[{"Name","Url","Logo"}]` (Windows and Linux compatible, may start with a UTF-8 BOM).
  - `history.json` has the shape `[{"Title","Station","Time"}]`, with Time as ISO 8601 to the second.
  - `preferences.json` keys: `Volume`, `LastPlayed`, `Language`, `ShowStationPopup`, `CheckUpdates`, `LastUpdateCheck` (ISO 8601), `UpdateByDownload`.
- **Text:**
  - UI strings are English in code, through `L("…")`.
  - Languages: `auto`, `pl`, `en`, `de`, `uk`, `cs`, `es`, `fr`, `it`, `pt`, in this order in the Language picker. Catalogues are `macos/Lang/<code>.po`.
- **Values copied from Windows/Linux:**
  - Reconnecting: backoff 2, 3, 5, 10, 15, 30 s; 10 retries once it has played, 2 before; the count resets after 60 s of playing; a network comeback counts within 10 min.
  - Sleep timer: 15, 30, 45, 60, 90 min; it fades out over the last 30 s.
  - Volume: steps of 5; menu presets Mute, 25, 50, 75, 100.
  - History keeps 100 entries; the cover cache keeps 200 files; a station switch settles after 0.3 s.
  - Update check every 6 h.
  - Tooltip and menu text are cut at 120 characters with "…".
- **Mac values:**
  - Panel content 412 × 602 pt; logos 40 pt (decoded at most 96 px).
  - The card shows for 3 s; "Copied" feedback lasts 1.5 s.
  - User-Agent `MinimalisticRadio/<version> (macOS)`. Network timeout 10 s; logos at most 2 000 000 bytes, covers at most 5 000 000.
- **Releases:**
  - Tags `macos-vX.Y.Z` and `macos-vX.Y.Z-beta.N`. Releases are created with `--latest=false`, betas as pre-releases.
  - Assets: `Minimalistic-Radio.dmg` (for people) and `Minimalistic-Radio-macOS.zip` (for the updater).
  - The fixed download pre-release has the tag `macos-download`.
- **Signing:**
  - Secrets `MACOS_SIGNING_CERTIFICATE` (a base64 .p12) and `MACOS_SIGNING_PASSWORD`.
  - The certificate's common name is `Minimalistic Radio (self-signed)`.
  - Only builds from `macos-v*` tags are signed with it; every other build is ad-hoc (`-`).
- **Size:** the `.app` is under 10 MB.
- **Network:** only the servers the README lists.

## Review Focus

1. **Plain-http stations and logos.** `http://stream.revma.ihrhls.com/zc185` (KIIS) must play and http logos must load. Without the ATS exception both fail quietly. A CI check in Task 1 asserts `NSAllowsArbitraryLoads`.
2. **The app run from the DMG or from Downloads** (read-only volume or App Translocation). The self-update must not try to swap the bundle there. It falls back to the DMG, and the panel asks the user to move the radio to Applications. Test `canSwapInPlace` in Task 6.
3. **A MacBook with a notch hides the menu bar icon.** Launching the app again (Spotlight, Finder) must still open the panel, placed at the top right. Test `panelOrigin` with a nil anchor in Task 6, and the reopen handler in Task 15.
4. **Offline at launch.** The update check, suggestions and covers fail quietly: no alert and no arrow, and the next check comes later. Test `UpdateState` after a failed fetch in Task 6.
5. **No stations yet** (first run). The menu's Play is disabled, the panel shows the empty state that leads to Add a station, and Siri/Shortcuts "Play" answers "Add a station first." Test `RadioController.play()` returning `false` in Task 8, and the intent's error in Task 13.

---

### Task 1: Project skeleton, icons and CI

**Files:**
- Create: `macos/project.yml`, `macos/Core/Package.swift`, `macos/Core/Sources/RadioCore/Version.swift`, `macos/Core/Tests/RadioCoreTests/VersionTests.swift`
- Create: `macos/App/Info.plist`, `macos/App/AppDelegate.swift`, `macos/App/Resources/Assets.xcassets/{Contents.json, MenuBarIcon.imageset/*, AppIcon.appiconset/Contents.json}`, `macos/tools/make_icons.sh`, `macos/App/Resources/AppIcon.svg`
- Create: `.github/workflows/macos.yml`, `macos/.gitignore` (`*.xcodeproj`, `build/`, generated icon PNGs)
- Modify: `.github/workflows/build.yml:6` (add `'macos/**'` and `'.github/workflows/macos.yml'` to `paths-ignore`)

**Interfaces:**
- Produces: `RadioCore.appVersion: String` (read from the main bundle's `CFBundleShortVersionString`, `"0.0.0"` in tests); the XcodeGen project with targets `RadioCore` (local package), `MinimalisticRadio` (app); scheme `MinimalisticRadio`; CI job `build` uploading artifact `Minimalistic-Radio-dmg`.

- [ ] **Step 1: Write the package and a first test.**
  - `Package.swift`: `swift-tools-version: 5.10`, platforms `.macOS(.v13)`, library `RadioCore`, test target `RadioCoreTests` using Swift Testing.
  - Test `@Test func versionFallsBackOutsideAnApp() { #expect(appVersion == "0.0.0") }`.
- [ ] **Step 2: Write `project.yml`.** It sets the Global Constraints' build settings, `MARKETING_VERSION: 1.0.0` and `MR_RELEASE_TAG: dev`.
  - It includes `../data/banned-stations.json` as an app resource.
  - It adds the local package `Core` as a dependency.
  - `options.preGenCommand: tools/make_icons.sh`.
- [ ] **Step 3: Make the icons.**
  - `AppIcon.svg`: a 1024 × 1024 squircle (corner radius 22.5 %) filled `#000`, with the four rounded bars of `linux/data/icons/hicolor/scalable/apps/io.github.zal3wa.minimalistic-radio.svg` (fill `#c8c8c8`) scaled to the middle 60 %.
  - `make_icons.sh` renders it with `rsvg-convert` into every size the `AppIcon.appiconset/Contents.json` lists (16–1024, @1x/@2x).
  - `MenuBarIcon.imageset` holds `linux/data/icons/hicolor/symbolic/apps/io.github.zal3wa.minimalistic-radio-symbolic.svg` with `"preserves-vector-representation": true` and `"template-rendering-intent": "template"`.
- [ ] **Step 4: Write `AppDelegate.swift`.**
  - `@main final class AppDelegate: NSObject, NSApplicationDelegate` with `static func main()`.
  - It shows an `NSStatusItem` with `MenuBarIcon` and a menu with Quit, and handles `--self-test`: exit 0 after building the status item.
- [ ] **Step 5: Write `macos.yml`.**
  - Triggers: `push` (branches `**`, tags `macos-v*`, paths `macos/**`, `.github/workflows/macos.yml`, `data/banned-stations.json`), `pull_request` with the same paths, and `workflow_dispatch`.
  - Job `build` steps:
    1. `brew install xcodegen librsvg`, then `cd macos && xcodegen generate`.
    2. `swift test --package-path macos/Core`.
    3. `xcodebuild -project macos/MinimalisticRadio.xcodeproj -scheme MinimalisticRadio -configuration Release -derivedDataPath build ARCHS="arm64 x86_64" ONLY_ACTIVE_ARCH=NO CODE_SIGN_IDENTITY=- MR_RELEASE_TAG="${TAG:-dev}" build`.
  - Checks:
    - `lipo -archs` prints both architectures;
    - `plutil -extract NSAppTransportSecurity.NSAllowsArbitraryLoads raw Info.plist` prints `true`;
    - `banned-stations.json` is in `Contents/Resources`;
    - `du -sk` of the app is under 10240 KB;
    - `"…/MacOS/Minimalistic Radio" --self-test` exits 0.
  - DMG: `hdiutil create -volname "Minimalistic Radio" -srcfolder <staging with the app and an /Applications symlink> -format UDZO Minimalistic-Radio.dmg`, uploaded as an artifact.
- [ ] **Step 6: Verify:** push `macos` and watch the run. Expected: PASS, and the artifact `Minimalistic-Radio-dmg` exists.
- [ ] **Step 7: Commit:** `macOS: project skeleton, icons and CI`.

### Task 2: Core models, storage and stream addresses

**Files:**
- Create: `macos/Core/Sources/RadioCore/{Models.swift, Storage.swift, Streams.swift}`
- Test: `macos/Core/Tests/RadioCoreTests/{StorageTests.swift, StreamsTests.swift}`

**Interfaces:**
- Produces:
  - `struct Station: Codable, Equatable, Hashable { var name: String; var url: String; var logo: String? }`, with the JSON keys `Name`, `Url`, `Logo`.
  - `struct Preferences: Equatable`, with `volume: Int = 30`, `lastPlayed: String?`, `language = "auto"`, `showStationPopup = true`, `checkUpdates = true`, `lastUpdateCheck: Date?` and `updateByDownload = false`.
  - `struct HistoryEntry: Equatable { title: String; station: String; time: Date }`.
  - `struct Paths { let support: URL; let cache: URL; static func standard() -> Paths; var stationsFile, preferencesFile, historyFile, logosFolder, coversFolder: URL }`.
  - `let historyLimit = 100`.
  - `func loadStations(_ url: URL) -> (stations: [Station], wasCorrupt: Bool)`, `func saveStations(_ url: URL, _ stations: [Station]) throws`, `func loadPreferences(_ url: URL) -> Preferences`, `func savePreferences(_ url: URL, _ p: Preferences) throws`, `func loadHistory(_ url: URL) -> [HistoryEntry]`, `func saveHistory(_ url: URL, _ e: [HistoryEntry]) throws`.
  - `func isWebURL(_ s: String?) -> Bool`, `func streamKey(_ s: String?) -> String`, `func sameStream(_ a: String?, _ b: String?) -> Bool`.

- [ ] **Step 1: Write the failing tests.**
  - Port every case of `linux/tests/unit/test_storage.py` except `test_default_paths_follow_xdg`.
  - In its place, `standardPathsAreInLibrary`: `Paths.standard().support.path` ends with `Library/Application Support/Minimalistic Radio`, and `.cache.path` ends with `Library/Caches/io.github.zal3wa.minimalistic-radio`.
  - Port every case of `linux/tests/unit/test_streams.py`.
- [ ] **Step 2: Verify the tests fail:** push and watch. Expected: FAIL, compile errors for the missing types.
- [ ] **Step 3: Implement.** Port `linux/minimalistic_radio/core/{models,storage,streams}.py`.
  - Reading strips a UTF-8 BOM.
  - Writing is atomic (`Data.write(to:options:.atomic)`).
  - A corrupt `stations.json` is moved to `stations.json.bad`.
  - `preferences.json` clamps Volume to 0…100 and ignores unknown language codes.
- [ ] **Step 4: Verify:** push and watch. Expected: PASS.
- [ ] **Step 5: Commit:** `macOS core: models, storage, stream addresses`.

### Task 3: Core titles, covers and playlists

**Files:**
- Create: `macos/Core/Sources/RadioCore/{Titles.swift, Covers.swift, Playlists.swift}`
- Test: `macos/Core/Tests/RadioCoreTests/{TitlesTests.swift, CoversTests.swift, PlaylistsTests.swift}`

**Interfaces:**
- Produces:
  - `func stationKind(_ url: String) -> String`, `func parseTitle(_ raw: String?, kind: String) -> String?`, `func artworkFromRaw(_ raw: String?) -> String?`, `func splitTrack(_ track: String?) -> (artist: String?, title: String?)`, `func radio357Title(_ payload: Any?) -> String?`, `let radio357URL = URL(string: "https://stream.radio357.pl/now/playing.json")!`.
  - `func itunesSearchURL(_ track: String) -> URL?`, `func sameArtist(_ wanted: String, _ found: String?) -> Bool`, `func pickCover(artist: String, payload: Any?) -> String?`, `final class CoverCache { func get(_ track: String) -> (known: Bool, url: String?); func put(_ track: String, _ url: String?) }`.
  - `func isPlaylistURL(_ url: String) -> Bool`, `func isPlaylistType(_ contentType: String?) -> Bool`, `func isHLS(_ text: String) -> Bool`, `func firstStream(_ text: String, baseURL: String) -> String?`.

- [ ] **Step 1: Write the failing tests:** port every case of `linux/tests/unit/test_titles.py`, `test_covers.py` and `test_playlists.py`.
- [ ] **Step 2: Verify the tests fail:** push and watch. Expected: FAIL (compile).
- [ ] **Step 3: Implement:** port `linux/minimalistic_radio/core/titles.py`, `core/covers.py` and `audio/playlists.py`. The regular expressions become `NSRegularExpression` with the same patterns.
- [ ] **Step 4: Verify:** push and watch. Expected: PASS.
- [ ] **Step 5: Commit:** `macOS core: titles, covers, playlists`.

### Task 4: Core directory: search, suggestions, bans, country

**Files:**
- Create: `macos/Core/Sources/RadioCore/Directory.swift`
- Test: `macos/Core/Tests/RadioCoreTests/DirectoryTests.swift`

**Interfaces:**
- Consumes: `Station`, `isWebURL`, `sameStream` (Task 2).
- Produces:
  - `struct DirectoryStation: Equatable`, with the fields of the Python dataclass.
  - `struct BanList { static let none: BanList; init(json: Data) throws }`.
  - `func parseResults(_ items: Any?, limit: Int = 30, bans: BanList) -> [DirectoryStation]`, `func isHidden(_ e: DirectoryStation, bans: BanList) -> Bool`, `func subtitle(_ e: DirectoryStation) -> String`, `func toStation(_ e: DirectoryStation) -> Station`.
  - `let directoryServers = ["de1.api.radio-browser.info", "nl1.api.radio-browser.info"]`, `func searchURL(server: String, query: String) -> URL`.
  - `let recommendedIDs: [String]` (copied verbatim from `linux/minimalistic_radio/core/directory.py:160`), `func recommendedURL(server:) -> URL`, `func popularURL(server: String, country: String?) -> URL`, `let popularShown = 15`.
  - `func looksLikeSpam(_ name: String?) -> Bool`, `func nameKey(_ name: String?) -> String`, `func cleanPopular(_ items: [DirectoryStation], recommended: [DirectoryStation], …) -> [DirectoryStation]`.
  - `func countryFor(language: String, systemCountry: String?) -> String?`, `func languageOf(_ languages: [String]) -> String`.
  - `func playable(codec: String?, hls: Bool) -> Bool`: MP3, AAC, AAC+ and unknown codecs, and **HLS allowed** (unlike Windows).
  - `enum DirectoryError: Error { case unavailable }`, `func search(_ query: String, bans: BanList, fetch: (URL) async throws -> Any) async throws -> [DirectoryStation]`, `func suggestions(country: String?, bans: BanList, fetch: (URL) async throws -> Any) async throws -> (recommended: [DirectoryStation], popular: [DirectoryStation])`.

- [ ] **Step 1: Write the failing tests.**
  - Port every case of `linux/tests/unit/test_directory.py` except the one that compares the two ban-list copies and the ones about `country_from_locale` (a Linux environment parser).
  - Add `hlsIsPlayableOnTheMac`: `#expect(playable(codec: "AAC", hls: true))`, `#expect(!playable(codec: "OGG", hls: false))`, `#expect(!playable(codec: "FLAC", hls: false))`.
- [ ] **Step 2: Verify the tests fail:** push and watch. Expected: FAIL (compile).
- [ ] **Step 3: Implement:** port `linux/minimalistic_radio/core/directory.py`. The system country on the Mac is `Locale.current.region?.identifier`, which the app passes in as `systemCountry`.
- [ ] **Step 4: Verify:** push and watch. Expected: PASS.
- [ ] **Step 5: Commit:** `macOS core: station directory`.

### Task 5: Core languages and the Mac catalogues

**Files:**
- Create: `macos/Core/Sources/RadioCore/Lang.swift`, `macos/App/Localization.swift`, `macos/tools/sync_po.py`, `macos/Lang/{pl,de,uk,cs,es,fr,it,pt}.po`
- Modify: `macos/project.yml` (`macos/Lang/*.po` as app resources in a `Lang` folder)
- Test: `macos/Core/Tests/RadioCoreTests/LangTests.swift`

**Interfaces:**
- Produces:
  - `let supportedLanguages = ["pl","en","de","uk","cs","es","fr","it","pt"]`, `func languagesFor(setting: String, system: [String]) -> [String]`.
  - `struct Catalog { init(po: String); func translate(_ s: String) -> String? }`, which reads `msgid`/`msgstr` pairs, multi-line strings and `\n`/`\"` escapes, and skips the header and empty msgstr.
  - `final class Localizer { var setting: String; init(catalogs: [String: Catalog], system: [String]); func text(_ s: String) -> String }`. It uses the first language from `languagesFor` that has a catalogue and the string, and falls back to English (the msgid).
  - In the app (`Localization.swift`): `func L(_ s: String) -> String`, a global that calls the shared `Localizer`.
    - It is built at launch from the bundled `Lang/*.po` and `Locale.preferredLanguages`, and its `setting` comes from `prefs.language`.
    - Changing `Localizer.setting` changes later calls at once (live switching).
  - `sync_po.py` (runs on Windows with Python 3):
    1. it collects every `L("…")` literal under `macos/App` (and `LocalizedStringResource` literals under `macos/App/Intents`);
    2. it fills `macos/Lang/<code>.po` from, in order, the existing Mac entry, `src/Lang/<code>.po`, then `linux/po/<code>.po`;
    3. it prints the msgids still untranslated per language (exit 0).

- [ ] **Step 1: Write the failing tests.**
  - Port every case of `linux/tests/unit/test_i18n.py` that covers `languages_for`.
  - Add `catalogParsesMultilineAndEscapes`: the input `msgid ""\nmsgstr "x"\n\nmsgid "A \"b\"\nc"\nmsgstr "Ą \"b\"\nć"` gives `translate("A \"b\"\nc") == "Ą \"b\"\nć"`.
  - Add `localizerSwitchesLive`: with catalogues `pl` {"Stop": "Zatrzymaj"} and `de` {"Stop": "Stopp"}, system `["pl"]`, then `setting = "auto"` gives `"Zatrzymaj"`, `setting = "de"` gives `"Stopp"`, and `setting = "en"` gives `"Stop"`.
- [ ] **Step 2: Verify the tests fail:** push and watch. Expected: FAIL (compile).
- [ ] **Step 3: Implement `Lang.swift` and `sync_po.py`.** Write the eight `.po` files with a gettext header and no entries yet; later tasks fill them by running the script.
- [ ] **Step 4: Verify:** run `python macos/tools/sync_po.py` locally, which is expected to report 0 msgids. Then push and watch. Expected: PASS.
- [ ] **Step 5: Commit:** `macOS core: languages and catalogues`.

### Task 6: Core updates, panel geometry and error classification

**Files:**
- Create: `macos/Core/Sources/RadioCore/{Updates.swift, Geometry.swift, PlayerErrors.swift}`
- Test: `macos/Core/Tests/RadioCoreTests/{UpdatesTests.swift, GeometryTests.swift, PlayerErrorsTests.swift}`

**Interfaces:**
- Produces:
  - `struct ReleaseTag: Comparable { let major, minor, patch: Int; let beta: Int?; init?(_ tag: String) }`. It accepts `macos-v1.2.3` and `macos-v1.2.3-beta.4`; `dev` gives nil. A beta sorts before the release of the same version.
  - `struct AvailableUpdate: Equatable { let tag: ReleaseTag; let tagName: String; let zip: URL; let dmg: URL; let page: URL }`.
  - `func newestUpdate(releases: Any?, current: ReleaseTag) -> AvailableUpdate?`. It skips drafts, tags that aren't `macos-v*` (so `macos-download` is skipped), and releases missing either asset. It considers betas only when `current.beta != nil`, and returns an update only when it is newer than `current`.
  - `let releasesURL = URL(string: "https://api.github.com/repos/zal3wa/minimalistic-radio/releases?per_page=30")!`, `func updateCheckDue(last: Date?, now: Date) -> Bool` (6 h).
  - `func canSwapInPlace(bundlePath: String, writable: Bool) -> Bool`: false under `/Volumes/`, false for paths containing `/AppTranslocation/`, otherwise `writable`.
  - `enum UpdateState: Equatable { case none, available(AvailableUpdate), downloading(Int), failed }`, and `func afterCheck(_ result: AvailableUpdate?, fetchFailed: Bool, previous: UpdateState) -> UpdateState`. A failed fetch keeps `previous`, except that `downloading` stays as it is.
  - `func panelOrigin(anchor: CGRect?, visibleFrame: CGRect, size: CGSize) -> CGPoint`. The panel's top edge is 4 pt below `anchor.minY`, horizontally centred on the anchor and clamped 8 pt inside `visibleFrame`. Without an anchor, the panel sits at the top right of `visibleFrame`, 8 pt from both edges.
  - `func classify(domain: String, code: Int, httpStatus: Int?) -> ErrorKind`. HTTP 401/403/404/410 give `.refused`. `AVFoundationErrorDomain` codes −11828 (format not recognised) and −11833 (decoder not found) give `.unsupported`. Everything else gives `.network`. (`ErrorKind` is defined here and reused by Task 7.)

- [ ] **Step 1: Write the failing tests.**

  ```swift
  @Test func betaSortsBeforeRelease() {
      #expect(ReleaseTag("macos-v1.0.0-beta.2")! < ReleaseTag("macos-v1.0.0")!)
      #expect(ReleaseTag("macos-v1.0.0-beta.2")! < ReleaseTag("macos-v1.0.0-beta.10")!)
      #expect(ReleaseTag("dev") == nil && ReleaseTag("v2.5.0") == nil && ReleaseTag("macos-download") == nil)
  }
  @Test func newestSkipsOtherSystemsDraftsAndBetasForStableUsers()
  // a releases array with v2.5.0, linux-v1.0.0-beta.5, macos-download, a draft macos-v1.0.2,
  // macos-v1.0.1-beta.1 and macos-v1.0.0, each with both assets:
  // current macos-v0.9.0 → tagName "macos-v1.0.0"; current macos-v1.0.0-beta.3 → "macos-v1.0.1-beta.1";
  // current macos-v1.0.0 → "macos-v1.0.1-beta.1" is NOT offered → nil
  @Test func releaseWithoutTheZipIsSkipped()
  @Test func checkIsDueAfterSixHours() // nil → true; 5 h 59 min → false; 6 h → true
  @Test func noSwapFromTheDmgOrTranslocation() {
      #expect(!canSwapInPlace(bundlePath: "/Volumes/Minimalistic Radio/Minimalistic Radio.app", writable: true))
      #expect(!canSwapInPlace(bundlePath: "/private/var/folders/x/AppTranslocation/ABC/d/Minimalistic Radio.app", writable: true))
      #expect(canSwapInPlace(bundlePath: "/Applications/Minimalistic Radio.app", writable: true))
      #expect(!canSwapInPlace(bundlePath: "/Applications/Minimalistic Radio.app", writable: false))
  }
  @Test func failedCheckKeepsTheArrowState() // afterCheck(nil, fetchFailed: true, previous: .available(u)) == .available(u); previous .none stays .none
  @Test func panelSitsUnderTheIconAndInsideTheScreen() // anchor (1500, 1080, 24, 24), visible (0, 0, 1728, 1080), size 412×602 → (1306, 454); anchor near the right edge → x clamped to 1728-8-412
  @Test func panelWithoutAnIconGoesTopRight() // nil anchor → (1728-8-412, 1080-8-602)
  @Test func errorsAreClassified() // NSURLErrorDomain -1009 → .network; httpStatus 403 → .refused; AVFoundationErrorDomain -11828 → .unsupported
  ```

- [ ] **Step 2: Verify the tests fail:** push and watch. Expected: FAIL (compile).
- [ ] **Step 3: Implement the three files** to the signatures above.
- [ ] **Step 4: Verify:** push and watch. Expected: PASS.
- [ ] **Step 5: Commit:** `macOS core: updates, panel placement, player errors`.

### Task 7: Core controller: stations, preferences, history, import/export

**Files:**
- Create: `macos/Core/Sources/RadioCore/Controller.swift`, `macos/Core/Tests/RadioCoreTests/Fakes.swift`
- Test: `macos/Core/Tests/RadioCoreTests/ControllerStationsTests.swift`

**Interfaces:**
- Consumes: Tasks 2–4 and 6 (`ErrorKind`).
- Produces (a port of `linux/minimalistic_radio/controller.py` lines 30–260 and 550–717):
  - `protocol AudioPlayer: AnyObject { func play(_ url: String); func stop(); func setVolume(_ percent: Int) }`, with the contract in the Python `Player` docstring.
  - `protocol Scheduler { func callLater(_ seconds: Double, _ block: @escaping () -> Void) -> AnyObject; func cancel(_ handle: AnyObject); func now() -> Date }`.
  - `typealias FetchJSON = (URL, @escaping (Any?) -> Void) -> Void`, `typealias FetchFile = (URL, URL, @escaping (Bool) -> Void) -> Void`.
  - `enum Status { ready, connecting, playing, retrying, stopped }`, `struct Change: OptionSet` (`state, stations, track, cover, history, volume, sleep, preferences, switched, message`), `enum AddResult { added, duplicate, invalid }`, `struct ImportResult { let added: Int; let error: String? }`.
  - `@MainActor final class RadioController`:
    - `init(player:scheduler:paths:fetch:fetchFile:localize:)`, where `localize` is `(String) -> String`, default identity;
    - properties `stations, current, status, message, notice, track, coverPath, prefs, volume, sleepAt, sleepMinutes, history, corruptStations`, plus `var stationName: String?`, `var effectiveVolume: Int`, `var active: Bool`;
    - methods `subscribe(_ listener: @escaping (Change) -> Void) -> Int`, `unsubscribe(_ id: Int)`, `start(autostart: Bool)`, `select(_ index: Int, switched: Bool = false)`, `nextStation()`, `previousStation()`, `addStation(_:) -> AddResult`, `updateStation(_ index: Int, _ s: Station) -> AddResult`, `moveStation(from: Int, to: Int)`, `removeStation(_:)`, `importStations(_ url: URL) -> ImportResult`, `exportStations(_ url: URL) -> Bool`, `setLanguage(_:)`, `setShowStationPopup(_:)`, `setCheckUpdates(_:)`, `setLastUpdateCheck(_:)`, `setUpdateByDownload(_:)`, `clearHistory()`.
  - `moveStation(from:to:)` replaces Python's `move_station(index, delta)`: drag-and-drop gives a destination index (SwiftUI `onMove` semantics: `to` is the insertion index before removal).

- [ ] **Step 1: Write the failing tests.**
  - Port `linux/tests/unit/fakes.py` to `Fakes.swift` (`FakePlayer`, `FakeScheduler` with `advance(_ seconds:)`, `FakeFetch`).
  - Port these cases of `test_controller.py`: `test_select_switches_only_while_playing`, `test_next_previous_wrap_and_flag_switch`, `test_add_station_rejects_invalid_and_duplicates`, `test_update_station_follows_the_playing_station`, `test_move_and_remove_keep_current_station` (rewritten for `moveStation(from:to:)`: moving the playing station from 0 to 3 keeps it playing at index 2), `test_import_merges_like_windows`, `test_export_writes_windows_list_and_reports_failure`, `test_save_failures_keep_the_controller_working`, `test_unknown_language_ignored`, `test_language_and_station_popup_saved`, `test_start_loads_files_and_reports_a_corrupt_station_list`, `test_history_skips_repeats_keeps_100_and_clears`.
- [ ] **Step 2: Verify the tests fail:** push and watch. Expected: FAIL (compile).
- [ ] **Step 3: Implement** these parts of the controller. The playback methods may be stubs that Task 8 fills.
- [ ] **Step 4: Verify:** push and watch. Expected: PASS.
- [ ] **Step 5: Commit:** `macOS core: controller stations, preferences, history`.

### Task 8: Core controller: playback, reconnecting, titles, covers, volume, sleep timer

**Files:**
- Modify: `macos/Core/Sources/RadioCore/Controller.swift`
- Test: `macos/Core/Tests/RadioCoreTests/ControllerPlaybackTests.swift`

**Interfaces:**
- Produces (a port of `controller.py` lines 261–549):
  - `@discardableResult func play() -> Bool`, which returns false and does nothing when there are no stations; `stop(message: String? = nil)`; `toggle()`;
  - `networkAvailable(wasDown: Bool = true)`, `resumed()`;
  - `onPlayerStarted()`, `onPlayerTitle(_ raw: String)`, `onPlayerError(_ kind: ErrorKind, detail: String)`, `onPlayerEOS()`;
  - `setVolume(_:)`, `toggleMute()`, `setSleepTimer(minutes: Int?)`, and `var coverPath: URL?`.

- [ ] **Step 1: Write the failing tests.**
  - Port every remaining case of `test_controller.py`, from `test_start_plays_last_station_unless_autostart` to `test_start_keeps_the_200_newest_covers`, minus those taken in Task 7.
  - Add `playWithoutStationsReturnsFalse`: a fresh controller with no stations gives `#expect(c.play() == false)`, `#expect(player.calls.isEmpty)`, `#expect(c.status == .ready)`.
- [ ] **Step 2: Verify the tests fail:** push and watch. Expected: FAIL.
- [ ] **Step 3: Implement** to the Python behaviour, with the Global Constraints values.
- [ ] **Step 4: Verify:** push and watch. Expected: PASS.
- [ ] **Step 5: Commit:** `macOS core: controller playback`.

### Task 9: Core menu model

**Files:**
- Create: `macos/Core/Sources/RadioCore/MenuModel.swift`
- Test: `macos/Core/Tests/RadioCoreTests/MenuModelTests.swift`

**Interfaces:**
- Consumes: `RadioController` (Tasks 7–8).
- Produces:
  - `struct MenuItem: Equatable { let id: String; let label: String; var enabled = true; var checked = false; var symbol: String? = nil; var children: [MenuItem] = [] }`, where an id of `"-"` means a separator.
  - `func buildMenu(_ c: RadioController, update: String?) -> [MenuItem]`, with the same ids, order and labels as `linux/minimalistic_radio/platform/menu_model.py`.
  - `func tooltip(_ c: RadioController) -> String`.
  - `func nowPlayingInfo(_ c: RadioController) -> (title: String, artist: String?, artwork: URL?)`, ported from `mpris_metadata`.
  - The `symbol` is an SF Symbol name in place of the Linux icon name: `play.fill`/`stop.fill`, `dot.radiowaves.left.and.right`, `speaker.wave.2`, `moon`, `gearshape`, `xmark`, `arrow.down.circle`.

- [ ] **Step 1: Write the failing tests:** port every case of `linux/tests/unit/test_menu_model.py`, with the MPRIS cases becoming `nowPlayingInfo` cases.
- [ ] **Step 2: Verify the tests fail:** push and watch. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Verify:** push and watch. Expected: PASS.
- [ ] **Step 5: Commit:** `macOS core: menu model`.

### Task 10: The player, scheduler and network on macOS

**Files:**
- Create: `macos/App/Platform/{StreamPlayer.swift, MainScheduler.swift, Network.swift, LogoCache.swift}`

**Interfaces:**
- Consumes: `AudioPlayer`, `Scheduler`, `FetchJSON`, `FetchFile` (Task 7), `classify` (Task 6), playlists (Task 3).
- Produces:
  - **`final class StreamPlayer: AudioPlayer`** with `init(onStarted:onTitle:onError:onEOS:)` and `let avPlayer: AVPlayer` (Task 12's AirPlay button binds to it).
    - Before playing, it resolves `.pls`/`.m3u` addresses: it fetches up to 64 KB and uses `firstStream`, but HLS text is handed to AVPlayer as it is.
    - Song titles come from `AVPlayerItemMetadataOutput` (identifier `.icyMetadataStreamTitle`, else `.commonIdentifierTitle`).
    - `onStarted` fires on the first `timeControlStatus == .playing`.
    - Errors come from item failure and `failedToPlayToEndTime`, classified by `classify`. A stall over 10 s counts as `.network`, and `didPlayToEndTime` is EOS.
    - Every callback carries a session number and is dropped when it is stale, which is the Player contract.
    - Volume is `avPlayer.volume = Float(percent) / 100` and persists across items.
  - **`final class MainScheduler: Scheduler`:** `DispatchWorkItem`s on the main queue.
  - **`Network`:**
    - `enum Network { static func fetchJSON(_:_:); static func fetchFile(_:_:_:); static func fetchData(_ url: URL, limit: Int) async throws -> Data; static let userAgent: String }`;
    - URLSession with a 10 s timeout, the Global Constraints' size limits, and callbacks on the main queue.
  - **`@MainActor final class LogoCache`:**
    - `func lookup(_ url: String?) -> (known: Bool, image: NSImage?)` and `func load(_ url: String, _ done: @escaping (NSImage?) -> Void)`, ported from `linux/minimalistic_radio/ui/logos.py` (disk cache under `paths.logosFolder`, retry after 300 s, at most 4 downloads at a time);
    - decoding with `CGImageSourceCreateThumbnailAtIndex` and `kCGImageSourceThumbnailMaxPixelSize` 96.

- [ ] **Step 1: Implement the four files** to the interfaces above.
- [ ] **Step 2: Extend `--self-test`** in `AppDelegate`: decode a 16 × 16 PNG made in memory through `LogoCache`'s decoder and check that the result is 16 × 16.
- [ ] **Step 3: Verify:** push and watch. Expected: PASS (it builds, the core tests pass, and the self-test exits 0).
- [ ] **Step 4: Commit:** `macOS: AVFoundation player, scheduler, network, logo cache`.

### Task 11: Menu bar item, menu, Now Playing, wake/network and login item

**Files:**
- Create: `macos/App/{StatusItemController.swift, MenuBuilder.swift}`, `macos/App/Platform/{NowPlaying.swift, SystemEvents.swift, LoginItem.swift}`
- Modify: `macos/App/AppDelegate.swift`

**Interfaces:**
- Consumes: `buildMenu`, `tooltip`, `nowPlayingInfo` (Task 9), `RadioController`, `StreamPlayer`, `MainScheduler`, `Network` (Task 10).
- Produces:
  - **`AppDelegate`:**
    - `static var shared: AppDelegate!` and `let controller: RadioController`, built at launch with `Paths.standard()`, `controller.start(autostart: <launched as a login item>)`;
    - `func openPanel(page: String? = nil)`, a no-op until Task 15;
    - `func showCard(_ text: String? = nil)`, a no-op until Task 18.
  - **`StatusItemController`:**
    - the template icon and the `tooltip` of the controller;
    - `sendAction(on: [.leftMouseUp, .rightMouseUp])`: a left click without Control calls `openPanel()`, a right click or Control-click pops up the `NSMenu` from `MenuBuilder`;
    - `var buttonFrameOnScreen: CGRect?`, which is nil when the item isn't visible.
  - **`MenuBuilder.make(_ items: [MenuItem], perform: (String) -> Void) -> NSMenu`:**
    - ids map to controller calls exactly as the Linux app's `tray.py` handler does;
    - clicking the song copies it to `NSPasteboard.general` and calls `showCard(L("Copied to clipboard"))`;
    - **temporary items for the risk beta** at the bottom: "Import station list…" (`NSOpenPanel` → `controller.importStations`) and "Open at login" (checked from `LoginItem.isEnabled`). Task 17 removes both.
  - **`NowPlaying`:** `MPNowPlayingInfoCenter` (title, artist, artwork from `coverPath`, `playbackState`) and `MPRemoteCommandCenter` (play → `play()`; pause and stop → `stop()`; toggle → `toggle()`; next/previous → `nextStation()`/`previousStation()`), updated on each `Change`.
  - **`SystemEvents`:** `NSWorkspace.didWakeNotification` calls `controller.resumed()`. `NWPathMonitor` calls `controller.networkAvailable(wasDown: true)` when the path becomes satisfied after being unsatisfied.
  - **`enum LoginItem { static var isEnabled: Bool; static func set(_ on: Bool) throws; static func openSettings() }`:** `SMAppService.mainApp`. `openSettings` calls `SMAppService.openSystemSettingsLoginItems()`.
  - **Launched at login:** `SMAppService.mainApp.status == .enabled` and the process was launched by launchd (`NSAppleEventManager` has no open event), in which case it doesn't play by itself, as on Windows.

- [ ] **Step 1: Implement** to the interfaces above, then run `python macos/tools/sync_po.py` and translate any msgids it lists in the eight `.po` files.
- [ ] **Step 2: Verify:** push and watch. Expected: PASS. The self-test now also builds the menu from a controller with two stations and checks that the ids `playback`, `stations`, `volume`, `sleep`, `settings` and `quit` are present.
- [ ] **Step 3: Commit:** `macOS: menu bar item, menu, Now Playing, wake and login item`.

### Task 12: Signing identity, release workflow and the updater

**Files:**
- Create: `macos/tools/make_signing_cert.sh` (run once on the development PC with Git Bash's `openssl`), `macos/App/Platform/Updater.swift`, `docs/MACOS-PUBLISHING.md`
- Modify: `.github/workflows/macos.yml`, `macos/App/MenuBuilder.swift`, `macos/App/AppDelegate.swift`

**Interfaces:**
- Consumes: `newestUpdate`, `updateCheckDue`, `canSwapInPlace`, `afterCheck`, `UpdateState`, `ReleaseTag` (Task 6); the controller's preferences setters (Task 7).
- Produces:
  - **`AppDelegate.updater: Updater`:** the one instance, which the menu and the panel header read.
  - **`@MainActor final class Updater`:**
    - `var state: UpdateState`, `func checkIfDue()` (at launch and hourly, when `prefs.checkUpdates` is on and the build's `MRReleaseTag` parses as a `ReleaseTag`), `func checkNow(completion: (String) -> Void)` (returns "You have the latest version." or "Couldn't check for updates.").
    - `func install()`:
      1. downloads the zip to a temporary folder and unpacks it with `/usr/bin/ditto -x -k`;
      2. checks the new app with `SecStaticCodeCheckValidity(newCode, [], requirementOfSelf)`, where the requirement comes from `SecCodeCopyDesignatedRequirement` on `SecCodeCopySelf`;
      3. Before the first swap on this Mac, the card says `L("macOS may ask once for permission to update the radio.")`, which is the spec's line that explains the prompt.
      4. if `canSwapInPlace(Bundle.main.bundlePath, writable: FileManager.isWritableFile(atPath: parent folder))` holds, calls `FileManager.default.replaceItemAt(Bundle.main.bundleURL, withItemAt: newApp)`, then relaunches through `/bin/sh -c "sleep 1; /usr/bin/open \"$0\" --args --resume"` and calls `NSApp.terminate`;
      5. otherwise, or on any error, downloads the DMG, opens it with `NSWorkspace.shared.open`, and sets `controller.setUpdateByDownload(true)`.
    - When `prefs.updateByDownload` is set, the label is "Download update" and `install()` goes straight to step 5.
  - **`--resume` launch argument:** plays the last station after start.
  - **The menu gets "Update"** (from `buildMenu(update:)`) while `state` is `.available`.

- [ ] **Step 1: Write `make_signing_cert.sh`.**
  - `openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes -subj "/CN=Minimalistic Radio (self-signed)" -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=critical,codeSigning" -keyout key.pem -out cert.pem`.
  - Then `openssl pkcs12 -export -legacy -inkey key.pem -in cert.pem -name "Minimalistic Radio (self-signed)" -passout pass:$PASSWORD -out signing.p12`.
  - It prints the base64 of `signing.p12` into a file, never to the terminal.
- [ ] **Step 2: Create the identity and the secrets.**
  - Run the script in a temporary folder outside the repository.
  - Set the secrets with `gh secret set MACOS_SIGNING_CERTIFICATE < signing.p12.b64` and `gh secret set MACOS_SIGNING_PASSWORD` (value from stdin).
  - Hand the folder to the owner to save `signing.p12` and the password in their password manager and delete it. Never print, log or commit the key or the password.
- [ ] **Step 3: Extend `macos.yml`.** On `macos-v*` tags:
  1. Import the .p12 into a temporary keychain (`security create-keychain`, `import -T /usr/bin/codesign`, `set-key-partition-list -S apple-tool:,apple:,codesign:`).
  2. Build with `MR_RELEASE_TAG=$GITHUB_REF_NAME`, then sign: `codesign --force --sign "Minimalistic Radio (self-signed)" --keychain $KC --timestamp=none`. If `codesign` refuses the untrusted certificate, add `sudo security add-trusted-cert -d -r trustRoot -p codeSign -k $KC cert.pem` before signing.
  3. Check that `codesign -d -r- …` shows `certificate leaf = H"…"`.
  4. Check that the tag's version without `-beta.N` equals `MARKETING_VERSION`, else fail.
  5. Make the DMG and `ditto -c -k --keepParent` the zip.
  6. Create the release: `gh release create $TAG Minimalistic-Radio.dmg Minimalistic-Radio-macOS.zip --latest=false` (plus `--prerelease` for betas) with notes from the tag message.
  7. Create `macos-download` if it's missing (`--prerelease --latest=false`, title "Minimalistic Radio for macOS (download link)"), then `gh release upload macos-download Minimalistic-Radio.dmg --clobber`.
  - `permissions: contents: write` only for the release job.
- [ ] **Step 4: Implement `Updater`** to the interface above.
- [ ] **Step 5: Write `docs/MACOS-PUBLISHING.md`** in the plain style of `docs/LINUX-PUBLISHING.md`: how to tag a Mac beta or release, what the secrets are, what to do if the key is lost (testers reinstall from the DMG), and why it's self-signed.
- [ ] **Step 6: Verify:** push and watch. Expected: PASS for the branch build (unsigned, no release). The signed path is verified in Task 14.
- [ ] **Step 7: Commit:** `macOS: self-signed releases and the updater`.

### Task 13: Shortcuts and Siri

**Files:**
- Create: `macos/App/Intents/{StationEntity.swift, RadioIntents.swift, RadioShortcuts.swift}`, `macos/tools/intents_strings.py`
- Modify: `macos/project.yml` (resources `macos/App/Resources/*.lproj/{Localizable.strings,AppShortcuts.strings}`, generated by `intents_strings.py` in `preGenCommand`; `.gitignore` them)

**Interfaces:**
- Consumes: `RadioController` through `AppDelegate.shared.controller`, `showCard` (Task 11).
- Produces:
  - **`struct StationEntity: AppEntity`:** `id` is the stream URL and `name` the station name, with `StationQuery: EntityStringQuery` over `controller.stations`.
  - **Intents:** `PlayIntent` (optional `station: StationEntity`), `StopIntent`, `NextStationIntent`, `PreviousStationIntent`, `SleepTimerIntent` (`minutes: Int`, 0 = off, else one of 15/30/45/60/90), `VolumeIntent` (`percent: Int` 0…100).
    - Each has `openAppWhenRun = false` and runs on the main actor.
    - A station switch calls `showCard()`.
    - `PlayIntent` with no stations throws an error whose message is `L("Add a station first.")`.
  - **`RadioShortcuts: AppShortcutsProvider`** with these phrases (each includes `\(.applicationName)`):
    - "Play \(\.$station) in \(.applicationName)";
    - "Play \(.applicationName)";
    - "Stop \(.applicationName)";
    - "Next station in \(.applicationName)".
  - **`intents_strings.py`:** writes `<lang>.lproj/Localizable.strings` (intent titles and the error) and `AppShortcuts.strings` (phrases) from `macos/Lang/<lang>.po`.

- [ ] **Step 1: Implement** the intents, entity and shortcuts. Run `sync_po.py`, translate the new msgids including the phrases, and run `intents_strings.py`.
- [ ] **Step 2: Extend the self-test:** `RadioShortcuts.appShortcuts.count == 4`. A `PlayIntent` performed with an empty controller throws, and its message equals `L("Add a station first.")` in the current language.
- [ ] **Step 3: Verify:** push and watch. Expected: PASS. The build log shows `appintentsmetadataprocessor` with no errors, and `Contents/Resources/Metadata.appintents` exists in the app (add this check to `macos.yml`).
- [ ] **Step 4: Commit:** `macOS: Shortcuts and Siri`.

### Task 14: Risk-check beta on the owner's Mac (checkpoint)

**Files:**
- Create: `docs/MACOS-TEST-CHECKLIST.md`, section "Risk checks (beta 1–3)"

- [ ] **Step 1: Write the checklist section.** One numbered step per spec risk, in plain words for someone who isn't a developer:
  1. download the DMG, drag it to Applications, open it, go through "Open Anyway", and write down the macOS version (Apple menu → About This Mac);
  2. in the radio menu, "Import station list…" with a list exported on Windows (Settings → Export…), then play Antyradio Hard, KIIS FM, Radio 357 and an RMF station, and note whether the song appears in the menu for each;
  3. the media keys, AirPods, and Control Center's Now Playing;
  4. "Open at login" on, log out and in: the icon is there and nothing plays;
  5. Shortcuts app → search "Minimalistic Radio": the actions are listed; Spotlight (macOS 26): "Play Minimalistic Radio";
  6. when beta 2 is out: the green "Update" in the menu, click it, note any macOS prompt; the radio restarts playing;
  7. when beta 3 is out: update again and note whether any prompt came back.
- [ ] **Step 2: Ask the owner for the OK** to tag `macos-v1.0.0-beta.1` on the `macos` branch. With the OK, push the tag and watch the run. Expected: a pre-release with both assets, `macos-download` updated, and Windows v2.5.0 still "latest" (`gh release view --json tagName` prints `v2.5.0`).
- [ ] **Step 3: Owner runs steps 1–5.** Record the answers in the checklist's results table.
- [ ] **Step 4: Tag `macos-v1.0.0-beta.2`, then `-beta.3`,** each on a new commit (bump nothing; any small commit) and each with the owner's OK. The owner runs steps 6 and 7.
- [ ] **Step 5: Apply the spec's fallbacks** for any risk that failed, as new tasks before Task 15:
  - Risk 1: the DMG update path becomes the default;
  - Risk 2: ICY titles through `AVAssetResourceLoader`;
  - Risk 3: the URL scheme `minimalistic-radio://`;
  - Risk 4: the Login Items instruction.

  Update the spec's Risks section with what was found. Commit: `macOS: risk check results`.

### Task 15: The panel: window, header, stations page, station sheet

**Files:**
- Create: `macos/App/Panel/{PanelController.swift, PanelView.swift, HeaderView.swift, StationsPage.swift, StationRow.swift, StationSheet.swift}`
- Modify: `macos/App/AppDelegate.swift` (`openPanel`, `applicationShouldHandleReopen` → `openPanel()`)

**Interfaces:**
- Consumes: `panelOrigin` (Task 6), `StatusItemController.buttonFrameOnScreen` (Task 11), `LogoCache` (Task 10), the controller.
- Produces:
  - **`PanelController`:**
    - an `NSPanel` subclass with `canBecomeKey` true, borderless with a 12 pt corner radius and `NSVisualEffectView` material `.popover`;
    - content size 412 × 602, placed by `panelOrigin`;
    - it activates the app on show, and closes on `windowDidResignKey`, on Esc, and on a second click on the icon.
  - **`PanelView`:** a `NavigationStack` with pages `stations` (root), `search`, `history` and `settings`, through `openPanel(page:)`. The footer (Task 16) sits below every page.
  - **`HeaderView`:**
    - `+ Station` (`plus`), History (`clock.arrow.circlepath`), Settings (`gearshape`) and Close (`xmark`);
    - the green update arrow (`arrow.down.circle.fill` in `.green`) while `Updater.state` is `.available`.
  - **`StationsPage`:**
    - A `List` with `onMove` → `controller.moveStation(from:to:)`. Each row shows the logo at 40 pt, or the `dot.radiowaves.left.and.right` symbol until the logo arrives.
    - Row identity is the stream URL, so logos don't reload when the list is reordered.
    - A click plays that station. The playing station gets a play mark in the accent colour.
    - The ⋯ `Menu` offers Edit (sheet) and Remove.
    - ⌘⌥↑/↓ move the selected station.
    - With no stations, it shows `L("Add a station")` with a button that opens the search page.
  - **`StationSheet`:** fields "Station name", "Stream address (HTTP or HTTPS)" and "Logo address (optional)"; Save and Cancel; the message "Enter a name and a valid stream address. The logo is optional." The `AddResult.duplicate` message is "This address is already on the list."

- [ ] **Step 1: Implement**, then run `sync_po.py` and translate.
- [ ] **Step 2: Extend the self-test:** create the panel offscreen with a controller holding 3 stations, check that the stations page shows 3 rows, and call `moveStation(from: 0, to: 3)` (the order changes and the current station is kept).
- [ ] **Step 3: Verify:** push and watch. Expected: PASS.
- [ ] **Step 4: Commit:** `macOS: panel and station list`.

### Task 16: Footer: now playing, volume row with AirPlay, Play/Stop

**Files:**
- Create: `macos/App/Panel/{FooterView.swift, NowPlayingCard.swift, VolumeRow.swift, AirPlayButton.swift}`

**Interfaces:**
- Consumes: `StreamPlayer.avPlayer` (Task 10), the controller.
- Produces:
  - **`NowPlayingCard`:**
    - the cover at 48 pt from `coverPath`, else the station logo, else a symbol;
    - the caption `L("Now playing")`, and the song (or the status text);
    - a copy button (`doc.on.doc`) that becomes `checkmark` with `L("Copied")` for 1.5 s.
  - **`VolumeRow`:**
    - a speaker `Button` (`speaker.slash.fill` at 0, otherwise `speaker.wave.1/2/3.fill` by thirds) that calls `toggleMute()`;
    - a `Slider` 0…100 in steps of 1 → `setVolume`, with the value shown in a small label above the thumb only while dragging;
    - a moon `Menu` with 15/30/45/60/90 min and Off, checked as in the tray menu;
    - `AirPlayButton`, an `NSViewRepresentable` wrapping `AVRoutePickerView` with `player = avPlayer`.
  - **Play/Stop:** a full-width `.borderedProminent` `.controlSize(.large)` button with `play.fill`/`stop.fill` and `L("Play")`/`L("Stop")`.

- [ ] **Step 1: Implement**, then run `sync_po.py` and translate.
- [ ] **Step 2: Verify:** push and watch. Expected: PASS.
- [ ] **Step 3: Commit:** `macOS: now playing, volume, AirPlay, play/stop`.

### Task 17: Search, history and settings pages

**Files:**
- Create: `macos/App/Panel/{SearchPage.swift, HistoryPage.swift, SettingsPage.swift, AboutView.swift}`
- Modify: `macos/App/MenuBuilder.swift` (remove the two temporary items from Task 11)

**Interfaces:**
- Consumes: `search`, `suggestions`, `countryFor`, `languageOf`, `toStation`, `subtitle`, `BanList` (Task 4); `LoginItem` (Task 11); `Updater` (Task 12); `Localizer` (Task 5).
- Produces:
  - **`SearchPage`:**
    - a search field and Search button (Return searches), and the link `L("Add by address")`;
    - results from `search` (ban list loaded from the app bundle's `banned-stations.json`, Network fetch), each row with logo, name, `subtitle`, and `+` or `checkmark` with `L("Already on your list")` when `sameStream` matches a saved station;
    - with an empty field, the sections `L("Recommended")`, `L("Popular in your country")` (or `L("Popular worldwide")` without a country) from `suggestions(countryFor(languageOf(<UI languages>), Locale.current.region?.identifier))`, loaded once per panel opening;
    - the messages `L("Searching…")`, `L("No results.")`, `L("The station directory is unavailable right now. Try again.")`;
    - ⌘F opens this page.
  - **`HistoryPage`:**
    - rows "song" and "station · HH:mm" (24 h in locales that use it, via `Date.FormatStyle`);
    - a ⋯ menu with Copy, Search on Spotify (`https://open.spotify.com/search/<query>`) and Search on YouTube (`https://www.youtube.com/results?search_query=<query>`), the query built as in `linux/minimalistic_radio/ui/history_page.py`;
    - `L("Clear history")`, and the empty text `L("Songs the radio plays will show up here.")`.
  - **`SettingsPage`** (`Form` `.formStyle(.grouped)`):
    - General: Language picker ("Same as system" + native names as on Windows), "Open at login" (`LoginItem`, refreshed on appear), "Show station changes";
    - Stations: "Station list" with Export… (`NSSavePanel`, `stations.json`) and Import… (`NSOpenPanel`), showing the `ImportResult` messages;
    - Updates: on/off and "Check now" with the result text;
    - About: version (`MRReleaseTag` or `MARKETING_VERSION`), MIT, a GitHub link;
    - Quit Minimalistic Radio.
    - Changing the language sets `Localizer.setting` and redraws the panel and menu at once.

- [ ] **Step 1: Implement**, then run `sync_po.py` and translate everything it lists.
- [ ] **Step 2: Verify:** push and watch. Expected: PASS.
- [ ] **Step 3: Commit:** `macOS: search, history and settings`.

### Task 18: Station change card, shortcuts and finishing touches

**Files:**
- Create: `macos/App/CardController.swift`
- Modify: `macos/App/AppDelegate.swift`, `macos/App/Panel/PanelController.swift`

**Interfaces:**
- Consumes: `panelOrigin` (Task 6), the controller's `Change.switched`.
- Produces:
  - **`CardController.show(text: String?)`:**
    - a borderless, non-activating, click-through `NSPanel` (material `.hudWindow`, 12 pt corners, about 320 × 72 pt), placed by `panelOrigin` under the icon;
    - the logo or cover, the station name, and the song or `text`; it stays 3 s, and a new one replaces it;
    - shown on `Change.switched` when `prefs.showStationPopup` is on, and always for `text` ("Copied to clipboard").
  - **Keyboard in the panel:** Esc goes back a page or closes, ⌘, opens Settings, ⌘F opens Search, ⌘W closes, ⌘Q quits, and Space toggles play while no text field has focus.
  - **Not in Applications:** when `Bundle.main.bundlePath` isn't under `/Applications` (or is translocated), the panel shows one line at the top: `L("Move Minimalistic Radio to Applications to get updates.")`.

- [ ] **Step 1: Implement**, then run `sync_po.py` and translate.
- [ ] **Step 2: Verify:** push and watch. Expected: PASS.
- [ ] **Step 3: Commit:** `macOS: station change card and keyboard`.

### Task 19: Screenshots, README and docs

**Files:**
- Create: `macos/App/Screenshots.swift`
- Modify: `.github/workflows/macos.yml` (a screenshot step uploading artifact `macos-screenshots`), `README.md`, `docs/screenshots/README.md`, `docs/BUILDING.md`, `docs/MACOS-TEST-CHECKLIST.md` (full feature checklist like `docs/LINUX-TEST-CHECKLIST.md`)
- Create: `docs/download-macos.svg` (the style of `docs/download-linux.svg`, label "Download for macOS")

**Interfaces:**
- Produces:
  - **The launch argument `--screenshot DIR`:**
    - temporary `Paths`, a silent `AudioPlayer`, real `Network`;
    - the stations, playing station, songs and "jazz" search of `linux/minimalistic_radio/selftest.py` (`SHOT_STATIONS`, `SHOT_PLAYING`, `SHOT_SONGS`, `SHOT_SEARCH`);
    - it waits up to 20 s per page for logos, the cover and results;
    - it renders the panel content of the pages stations, search, history and settings in light and dark at 2× (the content view's `cacheDisplay(in:to:)` into a bitmap of twice the point size), into `macos-<page>-<light|dark>.png`.
  - **The menu bar picture** (`macos-menu-<light|dark>.png`, 778 pt wide like the others): CI tries `screencapture` of the real open menu first. If the runner can't capture the screen, the owner takes it (⌘⇧3 with the menu open, and the assistant crops it).
  - **README:**
    - a third download button linking to `https://github.com/zal3wa/minimalistic-radio/releases/download/macos-download/Minimalistic-Radio.dmg`, and a sub-note line "macOS: not from Apple's store, so the first time choose *Open Anyway* in System Settings → Privacy & Security";
    - a `## macOS` section after Linux, laid out like it (intro, download button, wide menu picture, the 2×2 grid with `width="50%"` cells), with the Open Anyway steps;
    - Privacy: the same servers, plus the line about Siri; Uninstall: drag to the Bin, plus the Application Support and Caches folders and the Login Items entry.
  - **BUILDING.md:** a `## macOS` section covering XcodeGen, the CI-only build, `sync_po.py`, and links to `MACOS-PUBLISHING.md` and the checklist.

- [ ] **Step 1: Implement the screenshot mode and the CI step.** Push and watch. Expected: PASS and artifact `macos-screenshots` with 8 PNGs 824 px wide.
- [ ] **Step 2: Review the pictures and copy them to `docs/screenshots/`.** Write the README and the docs.
- [ ] **Step 3: Commit:** `macOS: screenshots, README and docs`.

### Task 20: First feature-complete beta (checkpoint)

- [ ] **Step 1: Ask the owner for the OK** to merge `macos` into `main` (fast-forward or a merge commit) and to tag `macos-v1.0.0-beta.4` on `main`.
- [ ] **Step 2: With the OK:** merge, push, tag, and watch the run. Expected: a pre-release with both assets, `macos-download` updated, `v2.5.0` still "latest", and the README's macOS button downloading the DMG.
- [ ] **Step 3: The owner updates beta 3 through the green arrow** and walks the full checklist. Fixes become new tasks.
