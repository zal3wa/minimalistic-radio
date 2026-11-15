import Foundation
@testable import RadioCore

// Test doubles for RadioController, ported from linux/tests/unit/fakes.py and conftest.py:
// a player, a clock with timers, and the network.

enum PlayerCall: Equatable {
    case play(String)
    case stop
    case setVolume(Int)
}

final class FakePlayer: AudioPlayer {
    var calls: [PlayerCall] = []
    func play(_ url: String) { calls.append(.play(url)) }
    func stop() { calls.append(.stop) }
    func setVolume(_ percent: Int) { calls.append(.setVolume(percent)) }
}

/// A clock that only moves on advance(), running the callbacks that fall due on the way.
final class FakeScheduler: Scheduler {
    final class Handle {
        let id: Int
        init(_ id: Int) { self.id = id }
    }

    let start = localDate(2026, 11, 14, 12, 0)
    private(set) var time: Double = 0
    private var timers: [Int: (due: Double, block: () -> Void)] = [:]
    private var nextID = 0

    func now() -> Date { start.addingTimeInterval(time) }

    func callLater(_ seconds: Double, _ block: @escaping () -> Void) -> AnyObject {
        nextID += 1
        timers[nextID] = (time + seconds, block)
        return Handle(nextID)
    }

    func cancel(_ handle: AnyObject) {
        if let handle = handle as? Handle { timers[handle.id] = nil }
    }

    var pending: Int { timers.count }

    func advance(_ seconds: Double) {
        let target = time + seconds
        while let next = timers.min(by: { ($0.value.due, $0.key) < ($1.value.due, $1.key) }), next.value.due <= target + 1e-9 {
            timers[next.key] = nil
            time = next.value.due
            next.value.block()
        }
        time = target
    }
}

/// fetch (JSON) and fetchFile (downloads). Answers at once from `responses`, otherwise waits for reply().
final class FakeFetch {
    var urls: [String] = []
    var responses: [String: Any?] = [:]
    var pending: [(url: String, callback: (Any?) -> Void)] = []
    var downloads: [(url: URL, path: URL, callback: (Bool) -> Void)] = []

    func fetch(_ url: URL, _ callback: @escaping (Any?) -> Void) {
        urls.append(url.absoluteString)
        if let response = responses[url.absoluteString] {
            callback(response)
        } else {
            pending.append((url.absoluteString, callback))
        }
    }

    /// Answers the oldest request still waiting (nil means it failed).
    func reply(_ payload: Any?) {
        pending.removeFirst().callback(payload)
    }

    func file(_ url: URL, _ path: URL, _ callback: @escaping (Bool) -> Void) {
        downloads.append((url, path, callback))
    }

    func finishDownload(ok: Bool = true) {
        let download = downloads.removeFirst()
        if ok {
            try? FileManager.default.createDirectory(at: download.path.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? Data("cover of \(download.url.absoluteString)".utf8).write(to: download.path)
        }
        download.callback(ok)
    }
}

// Sample stations (A, B and C are what a started rig has).
let A = Station(name: "Alpha", url: "http://a.example/live")
let B = Station(name: "Beta", url: "http://b.example/live", logo: "https://b.example/logo.png")
let C = Station(name: "Gamma", url: "https://c.example/stream")

/// A RadioController over fakes, with these files already saved (ctl_factory). Call start() yourself, or use started().
@MainActor
final class Rig {
    let player = FakePlayer()
    let scheduler = FakeScheduler()
    let net = FakeFetch()
    let paths: Paths
    let controller: RadioController

    init(stations: [Station] = [A, B, C], prefs: Preferences? = nil, history: [HistoryEntry]? = nil) {
        let root = tempFolder()
        paths = Paths(support: root.appendingPathComponent("support"), cache: root.appendingPathComponent("cache"))
        try! saveStations(paths.stationsFile, stations)
        if let prefs { try! savePreferences(paths.preferencesFile, prefs) }
        if let history { try! saveHistory(paths.historyFile, history) }
        controller = RadioController(player: player, scheduler: scheduler, paths: paths,
                                     fetch: net.fetch, fetchFile: net.file)
    }

    /// Started with these stations, as at login: nothing selected, nothing playing.
    static func started(stations: [Station] = [A, B, C], prefs: Preferences? = nil) -> Rig {
        let rig = Rig(stations: stations, prefs: prefs)
        rig.controller.start(autostart: true)
        return rig
    }

    var savedNames: [String] { loadStations(paths.stationsFile).stations.map(\.name) }
}

@MainActor
func playing(_ c: RadioController, _ index: Int = 0) {
    c.select(index)
    c.play()
    c.onPlayerStarted()
}

struct DiskFull: Error {}
