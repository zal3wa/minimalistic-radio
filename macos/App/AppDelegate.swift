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
    private(set) var panel: PanelController!
    private var card: CardController!

    func applicationDidFinishLaunching(_ notification: Notification) {
        AppDelegate.shared = self
        if CommandLine.arguments.contains("--self-test") {
            selfTest()
            return
        }
        if let index = CommandLine.arguments.firstIndex(of: "--screenshot"), CommandLine.arguments.count > index + 1 {
            let output = URL(fileURLWithPath: CommandLine.arguments[index + 1])
            Task { @MainActor in exit(await self.takeScreenshots(into: output)) }
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
    func setUp(paths: Paths, player: AudioPlayer, fetch: @escaping FetchJSON, fetchFile: @escaping FetchFile) {
        controller = RadioController(player: player, scheduler: MainScheduler(), paths: paths, fetch: fetch,
                                     fetchFile: fetchFile, localize: L)
        logos = LogoCache(folder: paths.logosFolder)
        panel = PanelController(model: PanelModel(controller: controller, logos: logos))
        card = CardController(controller: controller, logos: logos)
        statusItem = StatusItemController(controller: controller, onClick: { [weak self] in self?.togglePanel() },
                                          perform: { [weak self] in self?.perform($0) })
        updater = Updater(controller: controller)
        updater.onChange = { [weak self] in
            self?.statusItem.refresh()
            self?.panel.model.refresh()
        }
        updater.showCard = { [weak self] in self?.showCard($0) }
        statusItem.updateLabel = { [weak self] in self?.updater.label }
        controller.subscribe { [weak self] change in self?.changed(change) }
    }

    private func changed(_ change: Change) {
        if change.contains(.preferences) {
            localizer.setting = controller.prefs.language
            panel.model.refresh()
        }
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

    /// Opens the panel, on `page` ("search", "history", "settings") or the stations.
    func openPanel(page: String? = nil) {
        let pages: [String: PanelModel.Page] = ["search": .search, "history": .history, "settings": .settings]
        panel.show(page: page.flatMap { pages[$0] }, anchor: statusItem.buttonFrameOnScreen)
    }

    private func togglePanel() {
        panel.toggle(anchor: statusItem.buttonFrameOnScreen)
    }

    /// The station card: after a media key, menu or Shortcuts switch (if Settings allows it), or with `text`.
    func showCard(_ text: String? = nil) {
        guard text != nil || controller.prefs.showStationPopup else { return }
        card.show(text: text, anchor: statusItem.buttonFrameOnScreen)
    }

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

        showCard(L("Copied to clipboard"))
        panel.show(anchor: nil)
        if !panel.isVisible { failures.append("the panel doesn't open") }
        panel.model.page = .settings
        panel.model.back()
        if panel.model.page != .stations { failures.append("Esc on a page doesn't go back to the stations") }
        panel.model.back()
        if panel.isVisible { failures.append("Esc on the stations doesn't close the panel") }
        for (page, plays) in [(PanelModel.Page.search, false), (.station(nil), false), (.stations, true)] {
            panel.model.page = page
            if panel.model.spacePlays != plays { failures.append("Space on \(page) should \(plays ? "" : "not ")play") }
        }
        panel.model.addStation()
        if panel.model.page != .search { failures.append("+ Station doesn't open the search") }
        panel.model.page = .stations

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
