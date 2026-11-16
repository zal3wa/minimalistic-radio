import AppKit
import AVKit
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
    private(set) var statusItem: StatusItemController!
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
        // CI: the disk-image update check alone, on a DMG made from this app (Updater.checkDMG).
        if let index = CommandLine.arguments.firstIndex(of: "--check-update-dmg"), CommandLine.arguments.count > index + 2 {
            let arguments = CommandLine.arguments
            exit(Updater.checkDMG(URL(fileURLWithPath: arguments[index + 1]), tag: arguments[index + 2]))
        }
        if let index = CommandLine.arguments.firstIndex(of: "--menu-picture"), CommandLine.arguments.count > index + 1 {
            let output = URL(fileURLWithPath: CommandLine.arguments[index + 1])
            Task { @MainActor in exit(await self.takeMenuPictures(into: output)) }
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
        // Started to open a share link: the link's page asks first, so the last station doesn't start by itself.
        controller.start(autostart: launchedAtLogin || !pendingLinks.isEmpty)
        if CommandLine.arguments.contains("--resume") { controller.play() }
        updater.start()
        let links = pendingLinks
        pendingLinks = []
        for link in links { openShareLink(link) }
    }

    /// Share links that came before the radio was set up (it was started to open one).
    private var pendingLinks: [URL] = []

    /// minimalistic-radio://add?… from the link page (Info.plist's CFBundleURLTypes), the radio running or not.
    func application(_ application: NSApplication, open urls: [URL]) {
        guard controller != nil else {
            pendingLinks += urls
            return
        }
        for url in urls { openShareLink(url) }
    }

    /// The panel on the link's Shared station page; a station already on the list plays on the stations page.
    func openShareLink(_ url: URL) {
        guard let link = readShareLink(url.absoluteString) else { return }
        panel.model.openShared(link)
        panel.show(page: panel.model.page, anchor: statusItem.buttonFrameOnScreen)
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

    /// Quit (the menu, ⌘Q, Settings, an update, logging out): the listening statistics are saved.
    func applicationWillTerminate(_ notification: Notification) {
        controller?.willQuit()
    }

    // MARK: - Panel and card (Tasks 15 and 18)

    /// Opens the panel, on `page` ("search", "history", "settings", "statistics") or the stations.
    func openPanel(page: String? = nil) {
        let pages: [String: PanelModel.Page] = ["search": .search, "history": .history, "settings": .settings,
                                                "statistics": .statistics]
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
        for text in ["History", "Statistics", "Clear statistics", "Top artists", "{0} h {1} min", "Share",
                     "Add it to your stations?", "Add", "Play automatically"]
            where L(text) == text {
            failures.append("\"\(text)\" isn't translated into Polish")
        }
        localizer.setting = saved

        let pixels = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 16, pixelsHigh: 16, bitsPerSample: 8,
                                      samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                                      bytesPerRow: 0, bitsPerPixel: 0)
        let png = pixels?.representation(using: .png, properties: [:]) ?? Data()
        if LogoCache.decode(png)?.size != NSSize(width: 16, height: 16) { failures.append("a PNG logo doesn't decode") }
        failures += PictureSelfTest.run()

        showCard(L("Copied to clipboard"))
        panel.show(anchor: nil)
        if !panel.isVisible { failures.append("the panel doesn't open") }
        panel.model.page = .history
        panel.model.openStatistics()
        panel.model.back()
        if panel.model.page != .history { failures.append("Esc on Statistics doesn't go back to Song history") }
        panel.model.page = .settings
        panel.model.openStatistics()
        panel.model.back()
        if panel.model.page != .settings { failures.append("Esc on Statistics doesn't go back to Settings") }
        panel.model.back()
        if panel.model.page != .stations { failures.append("Esc on a page doesn't go back to the stations") }
        panel.model.back()
        if panel.isVisible { failures.append("Esc on the stations doesn't close the panel") }
        for (page, plays) in [(PanelModel.Page.search, false), (.station(nil), false), (.stations, true),
                              (.history, true), (.statistics, true)] {
            panel.model.page = page
            if panel.model.spacePlays != plays { failures.append("Space on \(page) should \(plays ? "" : "not ")play") }
        }
        panel.model.addStation()
        if panel.model.page != .search { failures.append("+ Station doesn't open the search") }
        failures += checkPanelLayout()
        panel.model.page = .stations

        // Statistics: a session from the start of audio, its song, saved on quitting; the page draws them.
        controller.select(0)
        controller.play()
        controller.onPlayerStarted()
        controller.onPlayerTitle("Queen - A Kind Of Magic")
        controller.willQuit()
        controller.stop()
        let statistics = loadStatistics(paths.statisticsFile)
        if statistics.sessions.count != 1 || statistics.songs.map(\.title) != ["Queen - A Kind Of Magic"] {
            failures.append("the statistics weren't saved to statistics.json (\(statistics.sessions.count) sessions, \(statistics.songs.count) songs)")
        }
        if summarizeStatistics(Self.sampleStatistics(now: Date()), period: .month, now: Date()).isEmpty {
            failures.append("the sample statistics show nothing this month")
        }

        failures += checkSharing()

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

    /// The panel's pages as drawn, as far as AppKit shows them (SwiftUI draws the rest itself): the player only on
    /// the stations page, and the Statistics page's All / Year / Month switch.
    private func checkPanelLayout() -> [String] {
        var failures: [String] = []
        for page in [PanelModel.Page.stations, .history, .settings, .statistics] {
            panel.show(page: page, anchor: nil)
            RunLoop.current.run(until: Date().addingTimeInterval(0.3))
            guard let view = panel.contentView else { continue }
            // The player's AirPlay button is an AppKit view: there exactly when the player is.
            if !views(of: AVRoutePickerView.self, in: view).isEmpty != (page == .stations) {
                failures.append("the player \(page == .stations ? "doesn't show" : "shows") on \(page)")
            }
            if page == .statistics {
                let control = views(of: NSSegmentedControl.self, in: view).first
                let labels = control.map { control in (0..<control.segmentCount).compactMap { control.label(forSegment: $0) } }
                if labels != [L("All"), L("Year"), L("Month")] {
                    failures.append("Statistics has no All / Year / Month switch (\(labels ?? []))")
                } else if control?.selectedSegment != 2 {
                    failures.append("Statistics doesn't open on Month")
                }
            }
        }
        panel.close()
        return failures
    }

    /// Share a station, through the app's own doors: a minimalistic-radio:// link opened into the running radio
    /// (the Shared station page; Cancel changes nothing; Add with Play automatically unchecked only adds, and the
    /// list shows it; a station already on the list is then only shown, with "Already on your list"; Add checked
    /// adds and plays, and a station already on the list then just plays; a link without a station says so), a web
    /// link pasted into + Station's field, and Share copying the link with "Link copied". Starts with the
    /// self-test's two stations, nothing playing.
    private func checkSharing() -> [String] {
        var failures: [String] = []
        let model = panel.model
        let schemes = (Bundle.main.object(forInfoDictionaryKey: "CFBundleURLTypes") as? [[String: Any]] ?? [])
            .flatMap { $0["CFBundleURLSchemes"] as? [String] ?? [] }
        if !schemes.contains("minimalistic-radio") { failures.append("Info.plist doesn't register minimalistic-radio:// links") }
        let count = controller.stations.count
        let hard = Station(name: "Antyradio Hard", url: "https://an05.cdn.eurozet.pl/ANTHAR.mp3")
        let shared = SharedStation(name: hard.name, url: hard.url, logo: nil)
        let open = { (link: String) in self.application(NSApp, open: [URL(string: link)!]) }

        open(shareAppLink(hard))
        if model.page != .shared(shared) || !panel.isVisible { failures.append("a share link doesn't open the Shared station page") }
        model.back()
        if model.page != .stations || controller.stations.count != count || controller.active
            || !controller.prefs.playSharedStations {
            failures.append("Cancel on a shared station changed something")
        }

        open(shareAppLink(hard))
        if case .shared(let station?) = model.page { model.addShared(station, play: false) }
        if controller.stations.count != count + 1 || controller.stations.last?.url != hard.url || controller.active
            || model.page != .stations || model.scrollTarget != hard.url || controller.prefs.playSharedStations
            || loadPreferences(controller.paths.preferencesFile).playSharedStations {
            failures.append("Add without Play automatically didn't only add the shared station and save the choice")
        }

        let known = controller.stations[1]
        let knownLink = shareAppLink(Station(name: "Another name",
                                             url: known.url.uppercased().replacingOccurrences(of: "/LIVE", with: "/live") + "/"))
        open(knownLink)
        if model.page != .stations || controller.active || model.pill != .alreadyOnTheList || model.scrollTarget != known.url
            || controller.stations.count != count + 1 {
            failures.append("a shared station already on the list isn't only shown with \"Already on your list\" (unchecked)")
        }

        let classic = Station(name: "RMF Classic", url: "http://31.192.216.8/RMFCLASSIC48")
        open(shareAppLink(classic))
        if case .shared(let station?) = model.page { model.addShared(station, play: true) }
        if controller.stations.count != count + 2 || controller.stations.last?.url != classic.url
            || controller.current != count + 1 || !controller.active || model.page != .stations
            || !controller.prefs.playSharedStations {
            failures.append("Add with Play automatically didn't add and play the shared station")
        }
        controller.stop()

        open(knownLink)
        if model.page != .stations || controller.current != 1 || !controller.active || controller.stations.count != count + 2 {
            failures.append("a shared station already on the list doesn't just play (checked)")
        }
        controller.stop()

        open("minimalistic-radio://add?n=Nothing+else")
        if model.page != .shared(nil) { failures.append("a link without a station doesn't say so") }

        model.page = .search
        let nowy = Station(name: "Radio Nowy Świat", url: "https://stream.nowyswiat.online/mp3")
        if !model.openSharedText(" " + shareLink(nowy) + "\n", complete: false)
            || model.page != .shared(SharedStation(name: nowy.name, url: nowy.url, logo: nil)) {
            failures.append("a web link pasted into + Station doesn't open the Shared station page")
        }
        if model.openSharedText("jazz", complete: true) { failures.append("a search is taken for a share link") }

        model.page = .stations
        model.share(controller.stations[0])
        if NSPasteboard.general.string(forType: .string) != shareLink(controller.stations[0]) || !model.linkCopied {
            failures.append("Share doesn't copy the station's link and say so")
        }
        panel.close()
        return failures
    }

    private func views<T: NSView>(of type: T.Type, in view: NSView) -> [T] {
        ((view as? T).map { [$0] } ?? []) + view.subviews.flatMap { views(of: type, in: $0) }
    }
}
