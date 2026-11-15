import AppKit
import RadioCore

/// `--screenshot DIR` (CI): the README pictures of the panel, light and dark, at 2×, with the same stations, songs,
/// cover and "jazz" search as the Windows and Linux pictures (linux/minimalistic_radio/selftest.py). Logos, the
/// cover and the search results come from the network, as on the other systems. Nothing plays; temporary files.
extension AppDelegate {
    static let shotStations = [
        Station(name: "102.7 KIIS FM Los Angeles", url: "http://stream.revma.ihrhls.com/zc185",
                logo: "https://i.iheart.com/v3/re/assets.brands/61d4a04fc786e58c38995162?ops=gravity(%22center%22),contain(360,360)&quality=80"),
        Station(name: "Radio Nowy Świat", url: "https://stream.nowyswiat.online/mp3",
                logo: "https://dabplus.live/logo/ea4141ebdcca43ef81e6f8e7351b4309.png"),
        Station(name: "Antyradio Hard", url: "https://an05.cdn.eurozet.pl/ANTHAR.mp3",
                logo: "https://gfx-player.radiozet.pl/var/player/storage/images/player-antyradio/kanaly-muzyczne/antyradio-hard/710016-10-pol-PL/Antyradio-Hard_size-228x228.jpg"),
        Station(name: "Radio 357", url: "https://stream.radio357.pl/",
                logo: "https://radio357.pl/wp-content/uploads/2022/04/c5399c0d-1b8e-43d5-b23b-e5cef1857856.png"),
        Station(name: "RMF Classic", url: "http://31.192.216.8/RMFCLASSIC48"),
        Station(name: "RMF Classic Rock", url: "https://rs201-krk.rmfstream.pl/rmf_classic_rock",
                logo: "https://www.rmfon.pl/assets/images/favicon/apple-touch-icon.png"),
        Station(name: "Polskie Radio Jedynka AAC", url: "http://stream3.polskieradio.pl:8950/;.mp3"),
        Station(name: "Polskie Radio - Czwórka (Program 4) (AAC+)", url: "http://stream3.polskieradio.pl:8956/;"),
    ]
    static let shotPlaying = 2
    /// (song, station) from the oldest; the last one is playing.
    static let shotSongs = [("Daughtry - What About Now", 7), ("Dawid Podsiadło - Małomiasteczkowy", 5),
                            ("Queen - A Kind Of Magic", 4), ("Editors - Shadow", 3), ("Leonard Cohen - Everybody Knows", 2)]

    func takeScreenshots(into output: URL) async -> Int32 {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("radio-shots-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        prepareShots(folder)
        try? FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        return await takePanelPictures(into: output)
    }

    /// The radio as in the README pictures: the stations, history and song of the other systems, nothing playing.
    private func prepareShots(_ folder: URL) {
        let paths = Paths(support: folder.appendingPathComponent("support"), cache: folder.appendingPathComponent("cache"))
        let now = Date()
        let older = Self.shotSongs.dropLast().reversed().map {
            HistoryEntry(title: $0.0, station: Self.shotStations[$0.1].name, time: now)
        }
        try? saveStations(paths.stationsFile, Self.shotStations)
        try? saveHistory(paths.historyFile, Array(older))
        localizer.setting = "en"
        setUp(paths: paths, player: SilentPlayer(), fetch: Network.fetchJSON, fetchFile: Network.fetchFile)
        panel.screenshotMode = true
        controller.start(autostart: true)
        controller.select(Self.shotPlaying)
        controller.play()
        controller.onPlayerStarted()
        controller.onPlayerTitle(Self.shotSongs.last!.0)
    }

    private func takePanelPictures(into output: URL) async -> Int32 {
        let model = panel.model
        var written = 0
        for (appearance, look) in [(NSAppearance.Name.aqua, "light"), (.darkAqua, "dark")] {
            NSApp.appearance = NSAppearance(named: appearance)
            for (page, name) in [(PanelModel.Page.stations, "stations"), (.search, "search"), (.history, "history"), (.settings, "settings")] {
                if page == .search {
                    model.lastResults = nil
                    model.pendingSearch = "jazz"
                }
                panel.show(page: page, anchor: nil)
                await wait(seconds: 20) {
                    switch page {
                    case .stations:
                        return self.controller.coverPath != nil && self.controller.stations.allSatisfy { self.logos.lookup($0.logo).known }
                    case .search:
                        guard let results = model.lastResults else { return false }
                        return results.allSatisfy { self.logos.lookup($0.logo).known }
                    default:
                        return true
                    }
                }
                // The directory sometimes doesn't answer: try the search again, twice at most.
                for _ in 0..<2 where page == .search && model.lastResults?.isEmpty != false {
                    model.lastResults = nil
                    model.pendingSearch = "jazz"
                    await wait(seconds: 20) { model.lastResults.map { $0.allSatisfy { self.logos.lookup($0.logo).known } } ?? false }
                }
                try? await Task.sleep(nanoseconds: 800_000_000)
                if let view = panel.contentView, render(view, to: output.appendingPathComponent("macos-\(name)-\(look).png")) {
                    written += 1
                }
            }
        }
        panel.close()
        print("wrote \(written) screenshots to \(output.path)")
        return written == 8 ? 0 : 1
    }

    /// `--menu-picture DIR`: the menu bar with the radio's open menu, light and dark (macos-menu-<look>.png),
    /// 778 points wide like the Windows and Ubuntu pictures, taken with screencapture while the menu is open.
    func takeMenuPictures(into output: URL) async -> Int32 {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("radio-menu-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        prepareShots(folder)
        try? FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        var written = 0
        for (dark, look) in [(false, "light"), (true, "dark")] {
            // The menu bar and its menus follow the system's look, not the app's: switch the system.
            Self.osascript("tell application \"System Events\" to tell appearance preferences to set dark mode to \(dark)")
            NSApp.appearance = nil
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            let full = output.appendingPathComponent("macos-menu-\(look)-full.png")
            var menuFrame: CGRect?
            let capture = Timer(timeInterval: 1.5, repeats: false) { _ in
                menuFrame = NSApp.windows.first { $0.isVisible && $0.className.contains("Menu") }?.frame
                let shot = Process()
                shot.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
                shot.arguments = ["-x", full.path]
                try? shot.run()
                shot.waitUntilExit()
                MainActor.assumeIsolated { self.statusItem.closeMenu() }
            }
            RunLoop.main.add(capture, forMode: .common)
            statusItem.showMenu()   // returns when the menu closes
            print("menu \(look): window \(menuFrame.map { "\($0)" } ?? "not found")")
            if crop(full, to: output.appendingPathComponent("macos-menu-\(look).png"), menu: menuFrame) { written += 1 }
        }
        print("wrote \(written) menu pictures to \(output.path)")
        return written == 2 ? 0 : 1
    }

    @discardableResult
    static func osascript(_ script: String) -> Bool {
        let run = Process()
        run.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        run.arguments = ["-e", script]
        try? run.run()
        run.waitUntilExit()
        print("osascript \(script.prefix(60))…: \(run.terminationStatus)")
        return run.terminationStatus == 0
    }

    /// The top right of the screen: 778 points wide, from the menu bar to just under the menu.
    private func crop(_ source: URL, to target: URL, menu: CGRect?) -> Bool {
        guard let image = NSImage(contentsOf: source)?.cgImage(forProposedRect: nil, context: nil, hints: nil),
              let screen = NSScreen.main else { return false }
        let scale = CGFloat(image.width) / screen.frame.width
        let bottom = menu.map { screen.frame.maxY - $0.minY + 24 } ?? 420
        let width = min(778, screen.frame.width)
        let rect = CGRect(x: (screen.frame.width - width) * scale, y: 0, width: width * scale, height: min(bottom, screen.frame.height) * scale)
        guard let cropped = image.cropping(to: rect.integral) else { return false }
        guard let png = NSBitmapImageRep(cgImage: cropped).representation(using: .png, properties: [:]) else { return false }
        return (try? png.write(to: target)) != nil
    }

    private func wait(seconds: Double, until ready: @escaping () -> Bool) async {
        let deadline = Date().addingTimeInterval(seconds)
        while !ready() && Date() < deadline {
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
    }

    /// The view at twice its size in points, as a PNG.
    private func render(_ view: NSView, to url: URL) -> Bool {
        let size = view.bounds.size
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width * 2), pixelsHigh: Int(size.height * 2),
                                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                         colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return false }
        rep.size = size
        view.cacheDisplay(in: view.bounds, to: rep)
        guard let png = rep.representation(using: .png, properties: [:]) else { return false }
        return (try? png.write(to: url)) != nil
    }
}
