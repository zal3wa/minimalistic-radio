import AppKit
import RadioCore
import UniformTypeIdentifiers

/// The radio lives in the menu bar (LSUIElement: no Dock icon, no menus of its own).
@main
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }

    static private(set) var shared: AppDelegate!

    private(set) var controller: RadioController!
    private(set) var player: StreamPlayer?
    private(set) var logos: LogoCache!
    private var statusItem: StatusItemController!
    private var nowPlaying: NowPlaying?
    private var systemEvents: SystemEvents?
    private(set) var updater: Updater!

    func applicationDidFinishLaunching(_ notification: Notification) {
        AppDelegate.shared = self
        if CommandLine.arguments.contains("--self-test") {
            selfTest()
            return
        }
        let launchedAtLogin = LoginItem.launchedAtLogin
        let paths = Paths.standard()
        let player = StreamPlayer(onStarted: { [weak self] in self?.controller.onPlayerStarted() },
                                  onTitle: { [weak self] in self?.controller.onPlayerTitle($0) },
                                  onError: { [weak self] in self?.controller.onPlayerError($0, detail: $1) },
                                  onEOS: { [weak self] in self?.controller.onPlayerEOS() })
        self.player = player
        setUp(paths: paths, player: player, fetch: Network.fetchJSON, fetchFile: Network.fetchFile)
        nowPlaying = NowPlaying(controller: controller)
        systemEvents = SystemEvents(controller: controller)
        controller.start(autostart: launchedAtLogin)
        if CommandLine.arguments.contains("--resume") { controller.play() }
        updater.start()
    }

    /// The controller, the logo cache and the menu bar item, over the given player and network.
    private func setUp(paths: Paths, player: AudioPlayer, fetch: @escaping FetchJSON, fetchFile: @escaping FetchFile) {
        controller = RadioController(player: player, scheduler: MainScheduler(), paths: paths, fetch: fetch,
                                     fetchFile: fetchFile, localize: L)
        logos = LogoCache(folder: paths.logosFolder)
        statusItem = StatusItemController(controller: controller, onClick: { [weak self] in self?.openPanel() },
                                          perform: { [weak self] in self?.perform($0) })
        statusItem.extraItems = { [weak self] in self?.riskCheckItems() ?? [] }
        updater = Updater(controller: controller)
        updater.onChange = { [weak self] in self?.statusItem.refresh() }
        updater.showCard = { [weak self] in self?.showCard($0) }
        statusItem.updateLabel = { [weak self] in self?.updater.label }
        controller.subscribe { [weak self] change in self?.changed(change) }
    }

    private func changed(_ change: Change) {
        if change.contains(.preferences) { localizer.setting = controller.prefs.language }
        statusItem.refresh()
        nowPlaying?.update()
        if change.contains(.switched) { showCard() }
        if change.contains(.message), let notice = controller.notice { showCard(notice) }
        if change.contains(.stations) { RadioShortcuts.updateAppShortcutParameters() }
    }

    /// Starting the radio again (Finder, Spotlight, the Dock) opens the panel, as on Windows.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openPanel()
        return false
    }

    // MARK: - Panel and card (Tasks 15 and 18)

    /// Until the panel exists (Task 15), a click shows the menu.
    func openPanel(page: String? = nil) {
        statusItem.showMenu()
    }

    func showCard(_ text: String? = nil) {}

    // MARK: - The menu's actions (the Linux tray's _on_menu)

    private func perform(_ id: String) {
        let c = controller!
        let parts = id.split(separator: ":", maxSplits: 1).map(String.init)
        let kind = parts[0], value = parts.count > 1 ? parts[1] : ""
        switch (kind, value) {
        case ("playback", _): c.toggle()
        case ("station", _): if let index = Int(value) { c.select(index, switched: true) }
        case ("volume", "up"): c.setVolume(c.volume + 5)
        case ("volume", "down"): c.setVolume(c.volume - 5)
        case ("volume", _): if let level = Int(value) { c.setVolume(level) }
        case ("sleep", "off"): c.setSleepTimer(minutes: nil)
        case ("sleep", _): if let minutes = Int(value) { c.setSleepTimer(minutes: minutes) }
        case ("now", "track"): copyTrack()
        case ("settings", _): openPanel(page: "settings")
        case ("update", _): updater.install()
        case ("quit", _): NSApp.terminate(nil)
        default: break
        }
    }

    func copyTrack() {
        guard let track = controller.track, !track.isEmpty else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(track, forType: .string)
        showCard(L("Copied to clipboard"))
    }

    // MARK: - Temporary menu items for the risk-check beta (removed when Settings exists, Task 17)

    private func riskCheckItems() -> [NSMenuItem] {
        [
            MenuBuilder.item(L("Import…")) { [weak self] in self?.importStations() },
            MenuBuilder.item(L("Open at login"), checked: LoginItem.isEnabled) {
                try? LoginItem.set(!LoginItem.isEnabled)
                if LoginItem.needsApproval { LoginItem.openSettings() }
            },
        ]
    }

    private func importStations() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        NSApp.activate(ignoringOtherApps: true)
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let result = controller.importStations(url)
        let alert = NSAlert()
        alert.messageText = result.error ?? "\(result.added)"
        alert.runModal()
    }

    // MARK: - Self-test

    /// `--self-test` (CI): the app's parts start on temporary files and a silent player, and build what they show;
    /// exit code 0 when everything is there. Nothing plays, and the user's files aren't touched.
    private func selfTest() {
        var failures: [String] = []
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("radio-self-test-\(UUID().uuidString)")
        let paths = Paths(support: folder.appendingPathComponent("support"), cache: folder.appendingPathComponent("cache"))
        try? saveStations(paths.stationsFile, [Station(name: "Radio 357", url: "http://s0.example/live"),
                                               Station(name: "RMF FM", url: "http://s1.example/live")])
        setUp(paths: paths, player: SilentPlayer(), fetch: { _, done in done(nil) }, fetchFile: { _, _, done in done(false) })
        controller.start(autostart: true)

        if !statusItem.hasIcon { failures.append("no menu bar icon") }
        if statusItem.makeMenu().items.count < 8 { failures.append("the menu bar menu is incomplete") }
        if updater.enabled != (Bundle.main.object(forInfoDictionaryKey: "MRReleaseTag") as? String ?? "dev").hasPrefix("macos-v") {
            failures.append("the updater doesn't follow the build's release tag")
        }
        let model = buildMenu(controller, update: nil).map(\.id)
        for id in ["playback", "stations", "volume", "sleep", "settings", "quit"] where !model.contains(id) {
            failures.append("the menu has no \(id)")
        }

        let saved = localizer.setting
        localizer.setting = "pl"
        if L("Quit") != "Zakończ" { failures.append("the Polish catalogue didn't load from the app bundle") }
        localizer.setting = saved

        let pixels = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 16, pixelsHigh: 16, bitsPerSample: 8,
                                      samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                                      bytesPerRow: 0, bitsPerPixel: 0)
        let png = pixels?.representation(using: .png, properties: [:]) ?? Data()
        if LogoCache.decode(png)?.size != NSSize(width: 16, height: 16) { failures.append("a PNG logo doesn't decode") }

        if RadioShortcuts.appShortcuts.count != 5 { failures.append("the Shortcuts are incomplete") }
        let empty = RadioController(player: SilentPlayer(), scheduler: MainScheduler(),
                                    paths: Paths(support: folder.appendingPathComponent("empty"), cache: folder.appendingPathComponent("empty-cache")),
                                    fetch: { _, done in done(nil) }, fetchFile: { _, _, done in done(false) }, localize: L)
        empty.start(autostart: true)
        do {
            try RadioIntents.play(nil, on: empty)
            failures.append("Play with no stations didn't say to add one")
        } catch let error as RadioIntentError {
            if String(localized: error.localizedStringResource) != L("Add a station first.") {
                failures.append("Play with no stations says something else")
            }
        } catch {
            failures.append("Play with no stations failed differently: \(error)")
        }

        let bans = BanList.load(Bundle.main.url(forResource: "banned-stations", withExtension: "json") ?? folder)
        if bans == .none { failures.append("the banned-stations list isn't in the app") }

        try? FileManager.default.removeItem(at: folder)
        for failure in failures { FileHandle.standardError.write(Data("self-test failed: \(failure)\n".utf8)) }
        exit(failures.isEmpty ? 0 : 1)
    }
}
