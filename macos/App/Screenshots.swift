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
        try? FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)

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
