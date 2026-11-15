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
        panel.model.showsUpdatesAlways = true                          // Settings as in a release
        panel.model.picturesMode = true                                // as installed: no Applications note
        panel.model.sampleStatistics = Self.sampleStatistics(now: now)  // in memory only
        controller.start(autostart: true)
        controller.select(Self.shotPlaying)
        controller.play()
        controller.onPlayerStarted()
        controller.onPlayerTitle(Self.shotSongs.last!.0)
    }

    private struct Shot {
        let page: PanelModel.Page
        let name: String
        var toEnd = false
        var update = false
        var statisticsOff = false
        var linkCopied = false
    }

    /// The station of the Shared station picture, as in the approved pictures.
    static let shotShared = SharedStation(name: shotStations[2].name, url: shotStations[2].url, logo: shotStations[2].logo)

    /// The README pictures, plus for review: the ends of Settings and Statistics, the top bar with an update,
    /// Statistics switched off, "Link copied" and a Shared station.
    private static let shots = [
        Shot(page: .stations, name: "stations"), Shot(page: .search, name: "search"), Shot(page: .history, name: "history"),
        Shot(page: .settings, name: "settings"), Shot(page: .settings, name: "settings-end", toEnd: true),
        Shot(page: .statistics, name: "statistics"), Shot(page: .statistics, name: "statistics-end", toEnd: true),
        Shot(page: .stations, name: "stations-update", update: true),
        Shot(page: .statistics, name: "statistics-off", statisticsOff: true),
        Shot(page: .stations, name: "stations-copied", linkCopied: true),
        Shot(page: .shared(shotShared), name: "shared"),
    ]

    private func takePanelPictures(into output: URL) async -> Int32 {
        let model = panel.model
        var written = 0
        var menus = 0
        var demos = 0
        var hotspots: [String: [String: [Int]]] = [:]
        for (appearance, look) in [(NSAppearance.Name.aqua, "light"), (.darkAqua, "dark")] {
            NSApp.appearance = NSAppearance(named: appearance)
            for shot in Self.shots {
                let page = shot.page, name = shot.name
                if page == .search {
                    model.lastResults = nil
                    model.pendingSearch = "jazz"
                }
                model.sampleUpdate = shot.update ? L("Update") : nil
                controller.setCollectStatistics(!shot.statisticsOff)   // temporary files: nothing of the user's
                if shot.linkCopied { model.showLinkCopied(for: nil) } else { model.hideLinkCopied() }
                model.refresh()
                panel.show(page: page, anchor: nil)
                await wait(seconds: 20) {
                    switch page {
                    case .stations:
                        return self.controller.coverPath != nil && self.controller.stations.allSatisfy { self.logos.lookup($0.logo).known }
                    case .search:
                        guard let results = model.lastResults else { return false }
                        return results.allSatisfy { self.logos.lookup($0.logo).known }
                    case .shared(let station):
                        return self.logos.lookup(station?.logo).known
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
                if shot.toEnd, let view = panel.contentView {
                    scrollToEnd(view)
                    try? await Task.sleep(nanoseconds: 500_000_000)
                }
                if let view = panel.contentView, render(view, to: output.appendingPathComponent("macos-\(name)-\(look).png")) {
                    written += 1
                }
            }
            model.hideLinkCopied()
            if await takeShareMenuPicture(output.appendingPathComponent("macos-share-menu-\(look).png"), dark: look == "dark") {
                menus += 1
            }
            let demo = await takeDemoPictures(into: output, look: look)
            demos += demo.written
            if look == "light" { hotspots = demo.hotspots }
        }
        model.sampleUpdate = nil
        panel.close()
        writeHotspots(hotspots, to: output.appendingPathComponent("macos-demo-hotspots.json"))
        // The menus are screen captures (each is a window of its own): reported, but not required.
        print("wrote \(written) screenshots, \(menus) share menu pictures and \(demos) demo pictures to \(output.path)")
        return written == Self.shots.count * 2 ? 0 : 1
    }

    // MARK: - The landing page's demo

    /// The landing page's demo, as the README pictures: the stations (the cursor goes to [History]), Song history (the
    /// first song's ⋯, [Statistics], ‹), the song's menu with Search on Spotify under the pointer, and Statistics (Month)
    /// opened from Song history (‹). With the pixel centres of those buttons, from the views' own frames.
    private func takeDemoPictures(into output: URL, look: String) async -> (written: Int, hotspots: [String: [String: [Int]]]) {
        let model = panel.model
        var written = 0
        var spots: [String: [String: [Int]]] = [:]
        func file(_ name: String) -> URL { output.appendingPathComponent("macos-demo-\(name)-\(look).png") }
        func show(_ page: PanelModel.Page) async {
            if page != .statistics { panel.show(page: page, anchor: nil) }
            model.refresh()
            try? await Task.sleep(nanoseconds: 900_000_000)
        }
        model.hideLinkCopied()
        model.sampleUpdate = nil
        controller.setCollectStatistics(true)

        await show(.stations)
        if let view = panel.contentView, render(view, to: file("stations")) { written += 1 }
        spots["macos-demo-stations"] = ["history": model.hotspots["history"].map(pixel)].compactMapValues { $0 }

        await show(.history)
        if let view = panel.contentView, render(view, to: file("history")) { written += 1 }
        let dots = firstRowMenuButton()
        spots["macos-demo-history"] = ["song-menu": dots.map(pixel), "statistics": model.hotspots["statistics"].map(pixel),
                                       "back": model.hotspots["back"].map(pixel)].compactMapValues { $0 }

        if let dots, let spotify = await takeSongMenuPicture(below: dots, file: file("history-menu"), dark: look == "dark") {
            written += 1
            spots["macos-demo-history-menu"] = ["search-on-spotify": spotify]
        }

        model.openStatistics()   // from Song history, as the demo's cursor does
        await show(.statistics)
        if let view = panel.contentView, render(view, to: file("statistics")) { written += 1 }
        spots["macos-demo-statistics"] = ["back": model.hotspots["back"].map(pixel)].compactMapValues { $0 }
        print("demo \(look): \(written) of 4 pictures, hotspots \(spots)")
        return (written, spots)
    }

    /// A frame in points from the panel's top left → the centre in the pictures' pixels (2×).
    private func pixel(_ rect: CGRect) -> [Int] {
        [Int((rect.midX * 2).rounded()), Int((rect.midY * 2).rounded())]
    }

    /// The first list row's ⋯ (SwiftUI's menu button is an AppKit pop-up button), in points from the panel's top left.
    private func firstRowMenuButton() -> CGRect? {
        guard let content = panel.contentView,
              let table = subviews(of: content).compactMap({ $0 as? NSTableView }).first, table.numberOfRows > 0 else { return nil }
        let row = content.convert(table.rect(ofRow: 0), from: table)
        let buttons = subviews(of: table)
            .filter { $0 is NSPopUpButton || String(describing: type(of: $0)).contains("Popup") }
            .map { content.convert($0.bounds, from: $0) }
            .filter { $0.intersects(row) }
        guard let button = buttons.max(by: { $0.midX < $1.midX }) else { return nil }
        return topLeft(button, in: content)
    }

    private func topLeft(_ rect: CGRect, in content: NSView) -> CGRect {
        content.isFlipped ? rect : CGRect(x: rect.minX, y: content.bounds.height - rect.maxY, width: rect.width, height: rect.height)
    }

    private func subviews(of view: NSView) -> [NSView] {
        view.subviews + view.subviews.flatMap { subviews(of: $0) }
    }

    /// Song history with the first song's ⋯ menu open (Copy, Search on Spotify, Search on YouTube, as HistoryRow's
    /// menu) and Search on Spotify under the pointer: the panel drawn as the other pictures (2×), and the menu, a
    /// window of its own, captured from the screen and laid on at its place. Returns Search on Spotify's pixel centre.
    private func takeSongMenuPicture(below dots: CGRect, file: URL, dark: Bool) async -> [Int]? {
        guard let window = panel.window, let content = panel.contentView else { return nil }
        let menu = NSMenu()
        menu.autoenablesItems = false
        menu.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        menu.addItem(withTitle: L("Copy"), action: nil, keyEquivalent: "")
        let spotify = menu.addItem(withTitle: L("Search on Spotify"), action: nil, keyEquivalent: "")
        menu.addItem(withTitle: L("Search on YouTube"), action: nil, keyEquivalent: "")
        // Just under the ⋯, and inside the panel.
        let left = min(dots.midX - 12, content.bounds.width - 8 - menu.size.width)
        let place = NSPoint(x: left, y: content.isFlipped ? dots.maxY + 2 : content.bounds.height - dots.maxY - 2)
        let screenTop = NSScreen.screens.first?.frame.maxY ?? 0
        let capture = FileManager.default.temporaryDirectory.appendingPathComponent("radio-menu-\(UUID().uuidString).png")
        defer { try? FileManager.default.removeItem(at: capture) }
        var menuFrame: CGRect?
        var itemCentre: CGPoint?
        var captured = false
        let point = Timer(timeInterval: 0.5, repeats: false) { _ in
            MainActor.assumeIsolated {
                guard let menuWindow = NSApp.windows.first(where: {
                    $0.isVisible && $0 !== window && String(describing: type(of: $0)).contains("Menu")
                }) else { return }
                menuFrame = menuWindow.frame
                let centre = self.menuItemCentre(spotify.title, in: menuWindow) ?? {
                    // Not found by its text: three equal rows inside 5 pt of padding.
                    print("demo: \(spotify.title) found by position, not by its view")
                    let frame = menuWindow.frame, height = (frame.height - 10) / 3
                    return CGPoint(x: frame.midX, y: frame.maxY - 5 - height * 1.5)
                }()
                itemCentre = centre
                CGWarpMouseCursorPosition(CGPoint(x: centre.x, y: screenTop - centre.y))   // highlights it
            }
        }
        let shot = Timer(timeInterval: 1.4, repeats: false) { _ in
            MainActor.assumeIsolated {
                if let number = NSApp.windows.first(where: {
                    $0.isVisible && $0 !== window && String(describing: type(of: $0)).contains("Menu")
                })?.windowNumber {
                    let run = Process()
                    run.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
                    run.arguments = ["-x", "-o", "-l\(number)", capture.path]
                    try? run.run()
                    run.waitUntilExit()
                    captured = run.terminationStatus == 0
                }
                menu.cancelTracking()
            }
        }
        RunLoop.main.add(point, forMode: .common)
        RunLoop.main.add(shot, forMode: .common)
        _ = menu.popUp(positioning: nil, at: place, in: content)   // returns when the menu closes
        try? await Task.sleep(nanoseconds: 300_000_000)

        guard captured, let menuFrame, let itemCentre,
              let menuImage = NSImage(contentsOf: capture)?.cgImage(forProposedRect: nil, context: nil, hints: nil),
              let panelImage = renderImage(content) else {
            print("demo: the song menu picture wasn't taken")
            return nil
        }
        let panelFrame = window.frame
        let scale = CGFloat(panelImage.width) / content.bounds.width
        guard let context = CGContext(data: nil, width: panelImage.width, height: panelImage.height, bitsPerComponent: 8,
                                      bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        context.interpolationQuality = .high
        context.draw(panelImage, in: CGRect(x: 0, y: 0, width: panelImage.width, height: panelImage.height))
        // Bottom-left origin: the menu's place in the panel, in pixels.
        context.draw(menuImage, in: CGRect(x: (menuFrame.minX - panelFrame.minX) * scale, y: (menuFrame.minY - panelFrame.minY) * scale,
                                           width: menuFrame.width * scale, height: menuFrame.height * scale))
        guard let composed = context.makeImage(),
              let png = NSBitmapImageRep(cgImage: composed).representation(using: .png, properties: [:]),
              (try? png.write(to: file)) != nil else { return nil }
        return [Int(((itemCentre.x - panelFrame.minX) * scale).rounded()), Int(((panelFrame.maxY - itemCentre.y) * scale).rounded())]
    }

    /// A menu item's row in an open menu's window, found by its title, as a screen point (its centre).
    private func menuItemCentre(_ title: String, in menuWindow: NSWindow) -> CGPoint? {
        guard let root = menuWindow.contentView?.superview ?? menuWindow.contentView else { return nil }
        for view in subviews(of: root) {
            let text = (view as? NSTextField)?.stringValue ?? view.accessibilityTitle() ?? view.accessibilityLabel()
            guard text == title else { continue }
            var row = view   // the row: the outermost view around the text that is still one item high
            while let parent = row.superview, parent !== root, parent.frame.height <= 32 { row = parent }
            let rect = row.convert(row.bounds, to: nil)
            return menuWindow.convertPoint(toScreen: CGPoint(x: rect.midX, y: rect.midY))
        }
        return nil
    }

    /// The same 2× picture as `render`, as an image.
    private func renderImage(_ view: NSView) -> CGImage? {
        let size = view.bounds.size
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width * 2), pixelsHigh: Int(size.height * 2),
                                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                         colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return nil }
        rep.size = size
        view.cacheDisplay(in: view.bounds, to: rep)
        return rep.cgImage
    }

    /// macos-demo-hotspots.json: per picture, the pixel centre of each place the demo's cursor clicks.
    private func writeHotspots(_ spots: [String: [String: [Int]]], to file: URL) {
        let document: [String: Any] = [
            "about": "Pixel centres (x, y from the top left) in the macos-demo-<name>-<light|dark>.png pictures, 2x.",
            "size": [Int(PanelController.size.width * 2), Int(PanelController.size.height * 2)],
            "frames": spots,
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: document, options: [.prettyPrinted, .sortedKeys]) else { return }
        try? data.write(to: file)
        print(String(decoding: data, as: UTF8.self))
    }

    /// The playing station's ⋯ menu (Edit, Share, a line, Remove) open over the panel with Share under the pointer,
    /// taken with screencapture: a menu is its own window, which the panel's picture doesn't include. The items are
    /// the ones StationRow's menu has.
    private func takeShareMenuPicture(_ file: URL, dark: Bool) async -> Bool {
        panel.show(page: .stations, anchor: nil)
        try? await Task.sleep(nanoseconds: 800_000_000)
        guard let window = panel.window, let content = panel.contentView, let screen = window.screen ?? NSScreen.main else {
            return false
        }
        let menu = NSMenu()
        menu.autoenablesItems = false
        menu.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        menu.addItem(withTitle: L("Edit"), action: nil, keyEquivalent: "")
        let share = menu.addItem(withTitle: L("Share"), action: nil, keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: L("Remove"), action: nil, keyEquivalent: "")
        // Share at the approved picture's place: under the ⋯ of the third station (top-left coordinates 264, 247).
        let place = NSPoint(x: 264, y: content.isFlipped ? 247 : content.bounds.height - 247)
        let onScreen = window.convertPoint(toScreen: content.convert(place, to: nil))
        let region = window.frame
        let top = screen.frame.maxY
        var written = false
        let point = Timer(timeInterval: 0.5, repeats: false) { _ in
            CGWarpMouseCursorPosition(CGPoint(x: onScreen.x + 20, y: top - onScreen.y))   // highlights Share
        }
        let capture = Timer(timeInterval: 1.5, repeats: false) { _ in
            let shot = Process()
            shot.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
            shot.arguments = ["-x", "-R", "\(Int(region.minX)),\(Int(top - region.maxY)),\(Int(region.width)),\(Int(region.height))", file.path]
            try? shot.run()
            shot.waitUntilExit()
            written = shot.terminationStatus == 0 && FileManager.default.fileExists(atPath: file.path)
            MainActor.assumeIsolated { menu.cancelTracking() }
        }
        RunLoop.main.add(point, forMode: .common)
        RunLoop.main.add(capture, forMode: .common)
        _ = menu.popUp(positioning: share, at: place, in: content)   // returns when the menu closes
        print("share menu \(dark ? "dark" : "light"): \(written ? "written" : "not written")")
        return written
    }

    /// Statistics for the pictures: evenings over about a year and a half with the pictures' stations and songs.
    /// Made up the same way on every run, kept in memory only.
    static func sampleStatistics(now: Date) -> StatisticsLog {
        var random = SampleRandom(seed: 357)
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: now)
        // (index in shotStations, weight, sends song titles)
        let stations: [(Int, Int, Bool)] = [(2, 36, true), (3, 24, true), (5, 17, true), (1, 12, false), (0, 7, true), (4, 4, false)]
        let songs = ["Leonard Cohen - Everybody Knows", "Editors - Shadow", "Queen - A Kind Of Magic", "Leonard Cohen - Suzanne",
                     "Dawid Podsiadło - Małomiasteczkowy", "Queen - Radio Ga Ga", "Daughtry - What About Now", "Editors - Papillon",
                     "Metallica - One", "Kult - Arahja", "Myslovitz - Długość dźwięku samotności", "Dżingiel"]
        var log = StatisticsLog()
        for back in stride(from: 620, through: 0, by: -1) {
            guard let day = calendar.date(byAdding: .day, value: -back, to: today) else { continue }
            var hours = [7, 12, 17, 18, 19, 19, 20, 20, 20, 20, 21, 21, 21, 22]   // evenings most often
            var picked: [Int] = []
            for _ in 0..<(random.next(upTo: 3) + (back < 40 ? 1 : 0)) {
                let hour = hours.remove(at: random.next(upTo: hours.count))
                hours.removeAll { $0 == hour }
                picked.append(hour)
            }
            picked.sort()
            for (number, hour) in picked.enumerated() {
                let start = day.addingTimeInterval(Double(hour * 60 + random.next(upTo: 30)) * 60)
                var end = start.addingTimeInterval(Double(20 + random.next(upTo: 100) + random.next(upTo: 100)) * 60)
                if number + 1 < picked.count { end = min(end, day.addingTimeInterval(Double(picked[number + 1]) * 3600 - 600)) }
                guard end > start, end < now else { continue }
                var pick = random.next(upTo: stations.map(\.1).reduce(0, +))
                let (index, _, titles) = stations.first { pick -= $0.1; return pick < 0 } ?? stations[0]
                let station = shotStations[index]
                log.sessions.append(ListeningSession(station: station.name, url: station.url, start: start, end: end, titles: titles))
                var time = start.addingTimeInterval(90)
                while titles && time < end {
                    let song = min(random.next(upTo: songs.count), random.next(upTo: songs.count))
                    log.songs.append(PlayedSong(station: station.name, title: songs[song], time: time))
                    time.addTimeInterval(Double(190 + random.next(upTo: 90)))
                }
            }
        }
        return log
    }

    /// Scrolls every list and scroll view in `view` to its end (the bottom of Settings and Statistics).
    private func scrollToEnd(_ view: NSView) {
        if let scroll = view as? NSScrollView, let document = scroll.documentView {
            let clip = scroll.contentView
            let end = document.isFlipped ? max(0, document.frame.height - clip.bounds.height + scroll.contentInsets.bottom) : 0
            clip.scroll(to: NSPoint(x: clip.bounds.minX, y: end))
            scroll.reflectScrolledClipView(clip)
        }
        for subview in view.subviews { scrollToEnd(subview) }
    }

    /// `--menu-picture DIR`: the menu bar with the radio's open menu, light and dark (macos-menu-<look>.png),
    /// taken with screencapture while the menu is open.
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

    /// The top right of the screen: 600 points wide, from the menu bar to just under the menu.
    private func crop(_ source: URL, to target: URL, menu: CGRect?) -> Bool {
        guard let image = NSImage(contentsOf: source)?.cgImage(forProposedRect: nil, context: nil, hints: nil),
              let screen = NSScreen.main else { return false }
        let scale = CGFloat(image.width) / screen.frame.width
        let bottom = menu.map { screen.frame.maxY - $0.minY + 24 } ?? 420
        let width = min(600, screen.frame.width)   // the Finder's own menus stay out
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

/// SplitMix64: the same made-up statistics on every run.
private struct SampleRandom {
    var state: UInt64

    init(seed: UInt64) {
        state = seed
    }

    mutating func next(upTo bound: Int) -> Int {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        z ^= z >> 31
        return Int(z % UInt64(max(bound, 1)))
    }
}
