import Foundation

// The radio itself: what plays, reconnecting, the sleep timer, song history and the station list.
// A port of linux/minimalistic_radio/controller.py (itself a port of src/Radio/RadioApp.cs). Everything runs on the
// main thread. Nothing here imports AppKit: the player, the timers and the network are handed in, so the tests drive
// it with fakes.

public let appName = "Minimalistic Radio"
let backoff: [Double] = [2, 3, 5, 10, 15, 30]          // seconds before each retry
let retriesOncePlayed = 10, retriesNeverPlayed = 2
let longConnection: TimeInterval = 60                   // a connection that lasted longer resets the retry count
let networkReturnWindow: TimeInterval = 10 * 60
let fadeSeconds: Double = 30                            // the sleep timer fades out over its last 30 seconds
let radio357PollSeconds: Double = 10
let coversKept = 200                                    // pictures kept in the cover cache
let volumeBurst: TimeInterval = 1                       // volume changes closer than this are one (a drag, keys)
let switchSettle: Double = 0.3                          // a media key or menu switch connects once switching pauses

public enum Status: Sendable {
    case ready, connecting, playing, retrying, stopped
}

public struct Change: OptionSet, Sendable {
    public let rawValue: Int
    public init(rawValue: Int) { self.rawValue = rawValue }

    /// The status, its message or the chosen station.
    public static let state = Change(rawValue: 1 << 0)
    public static let stations = Change(rawValue: 1 << 1)
    public static let track = Change(rawValue: 1 << 2)
    public static let cover = Change(rawValue: 1 << 3)
    public static let history = Change(rawValue: 1 << 4)
    public static let volume = Change(rawValue: 1 << 5)
    public static let sleep = Change(rawValue: 1 << 6)
    public static let preferences = Change(rawValue: 1 << 7)
    /// The station was changed by a media key, the menu or Shortcuts.
    public static let switched = Change(rawValue: 1 << 8)
    /// A notice for the user (the station list couldn't be saved).
    public static let message = Change(rawValue: 1 << 9)
}

public enum AddResult: Sendable {
    case added, duplicate, invalid
}

public struct ImportResult: Equatable, Sendable {
    public let added: Int
    public let error: String?

    public init(added: Int, error: String?) {
        self.added = added
        self.error = error
    }
}

/// The audio player. The controller relies on this contract:
/// - once play() or stop() returns, no callback (onPlayerStarted, …Title, …Error, …EOS) for an earlier stream arrives;
/// - callbacks never come synchronously from inside play(), stop() or setVolume();
/// - the volume from setVolume() persists across play() calls (the controller doesn't send it again when it connects).
public protocol AudioPlayer: AnyObject {
    func play(_ url: String)
    func stop()
    func setVolume(_ percent: Int)
}

public protocol Scheduler: AnyObject {
    func callLater(_ seconds: Double, _ block: @escaping () -> Void) -> AnyObject
    func cancel(_ handle: AnyObject)
    func now() -> Date
}

/// JSON from the network, calling back on the main thread with nil on any failure.
public typealias FetchJSON = (URL, @escaping (Any?) -> Void) -> Void
/// A download to a file, calling back on the main thread with whether it worked.
public typealias FetchFile = (URL, URL, @escaping (Bool) -> Void) -> Void

@MainActor
public final class RadioController {
    public let player: AudioPlayer
    public let scheduler: Scheduler
    public let paths: Paths
    let fetch: FetchJSON
    let fetchFile: FetchFile
    let localize: (String) -> String

    public private(set) var stations: [Station] = []
    public private(set) var current = -1
    public private(set) var status = Status.ready
    /// The status's own text ("Connection lost…"), nil for the usual one.
    public private(set) var message: String?
    /// The last notice, sent with `.message`; never a status.
    public private(set) var notice: String?
    public internal(set) var track: String?
    public private(set) var coverPath: URL?
    public private(set) var prefs = Preferences()
    public private(set) var volume = Preferences().volume
    public private(set) var sleepAt: Date?
    public private(set) var sleepMinutes: Int?
    public private(set) var history: [HistoryEntry] = []
    public private(set) var corruptStations = false
    /// Set when the retries ran out on network errors: networkAvailable() starts again within 10 minutes.
    public private(set) var gaveUpOnNetworkAt: Date?

    // Saving, replaceable in tests.
    var writeStations: (URL, [Station]) throws -> Void = saveStations
    var writePreferences: (URL, Preferences) throws -> Void = savePreferences
    var writeHistory: (URL, [HistoryEntry]) throws -> Void = saveHistory

    private var listeners: [Int: (Change) -> Void] = [:]
    private var nextListener = 0
    private var fade = 100
    // The playback session: one per play(), until stop() or the next play().
    private var session = 0
    private var url = ""
    private var kind = "generic"
    private var everPlayed = false

    public init(player: AudioPlayer, scheduler: Scheduler, paths: Paths, fetch: @escaping FetchJSON,
                fetchFile: @escaping FetchFile, localize: @escaping (String) -> String = { $0 }) {
        self.player = player
        self.scheduler = scheduler
        self.paths = paths
        self.fetch = fetch
        self.fetchFile = fetchFile
        self.localize = localize
    }

    /// Named L so that sync_po.py finds these texts too.
    private func L(_ english: String) -> String { localize(english) }

    // MARK: - State

    public var stationName: String? {
        stations.indices.contains(current) ? stations[current].name : nil
    }

    /// What the player gets: the chosen volume, lowered while the sleep timer fades out.
    public var effectiveVolume: Int { volume * fade / 100 }

    /// A station is on (connecting, playing or waiting to retry): the menu offers Stop.
    public var active: Bool { [.connecting, .playing, .retrying].contains(status) }

    @discardableResult
    public func subscribe(_ listener: @escaping (Change) -> Void) -> Int {
        nextListener += 1
        listeners[nextListener] = listener
        return nextListener
    }

    public func unsubscribe(_ id: Int) {
        listeners[id] = nil
    }

    func emit(_ change: Change) {
        guard !change.isEmpty else { return }
        for key in listeners.keys.sorted() { listeners[key]?(change) }
    }

    // MARK: - Files

    /// Loads the files and, unless started at login, plays the last station.
    public func start(autostart: Bool) {
        let loaded = loadStations(paths.stationsFile)
        stations = loaded.stations
        corruptStations = loaded.wasCorrupt
        prefs = loadPreferences(paths.preferencesFile)
        history = loadHistory(paths.historyFile)
        volume = prefs.volume
        current = stations.firstIndex { $0.url == prefs.lastPlayed } ?? -1
        player.setVolume(effectiveVolume)
        emit([.state, .stations, .volume, .history, .preferences])
        if current >= 0 && !autostart { play() }
    }

    // Saving never stops the radio. Only a station list that couldn't be saved is worth telling (as Windows).
    private func stationsChanged(_ extra: Change = []) {
        var changes: Change = [.stations, extra]
        do {
            try writeStations(paths.stationsFile, stations)
        } catch {
            notice = L("Couldn't save the station list.")
            changes.insert(.message)
        }
        emit(changes)
    }

    func savePrefs() {
        try? writePreferences(paths.preferencesFile, prefs)
    }

    private func saveHistoryFile() {
        try? writeHistory(paths.historyFile, history)
    }

    // MARK: - Playback

    /// Starts the chosen station (the first one if none is chosen). A station already on keeps going.
    public func play() {
        if !active { startSession() }
    }

    /// A new connection to the chosen station, dropping the current one (StartPlayback on Windows).
    func startSession() {
        guard !stations.isEmpty else { return }
        if !stations.indices.contains(current) { current = 0 }
        endSession()
        url = stations[current].url
        kind = stationKind(url)
        everPlayed = false
        connect()
        emit([.state, .track, .cover])
    }

    public func stop(message: String? = nil) {
        endSession()
        player.stop()
        status = .stopped
        self.message = message
        emit([.state, .track, .cover])
    }

    public func toggle() {
        if active { stop() } else { play() }
    }

    /// Forgets the current session: callbacks still on their way are ignored from now on.
    private func endSession() {
        session += 1
        gaveUpOnNetworkAt = nil
        track = nil
        coverPath = nil
    }

    private func connect() {
        status = .connecting
        message = nil
        player.play(url)
    }

    // MARK: - Called by the player (on the main thread)

    private func connected() -> Bool {
        status == .connecting || status == .playing
    }

    public func onPlayerStarted() {
        guard status == .connecting else { return }
        everPlayed = true
        status = .playing
        message = nil
        prefs.lastPlayed = url
        savePrefs()
        emit(.state)
    }

    public func onPlayerTitle(_ raw: String) {
        // Radio 357 sends a fixed slogan in the stream; its songs come from playing.json.
        if connected() && kind != "radio357" { showTrack(raw) }
    }

    public func onPlayerError(_ kind: ErrorKind, detail: String) {
        guard connected() else { return }
        stop(message: detail)
    }

    public func onPlayerEOS() {
        guard connected() else { return }
        stop(message: L("The broadcast has ended"))
    }

    // MARK: - Titles, history

    private func showTrack(_ raw: String?) {
        let title = parseTitle(raw, kind: kind)
        if title == track { return }
        track = title
        coverPath = nil
        var changes: Change = [.track, .cover]
        if let title, addToHistory(title) { changes.insert(.history) }
        emit(changes)
    }

    private func addToHistory(_ title: String) -> Bool {
        let station = stationName ?? appName
        if let first = history.first, first.title == title, first.station == station { return false }
        history.insert(HistoryEntry(title: title, station: station, time: scheduler.now()), at: 0)
        if history.count > historyLimit { history.removeLast(history.count - historyLimit) }
        saveHistoryFile()
        return true
    }

    public func clearHistory() {
        history.removeAll()
        saveHistoryFile()
        emit(.history)
    }

    // MARK: - Volume

    public func setVolume(_ percent: Int) {
        let value = max(0, min(100, percent))
        guard value != volume else { return }
        volume = value
        prefs.volume = value
        player.setVolume(effectiveVolume)
        savePrefs()
        emit(.volume)
    }

    // MARK: - Choosing a station

    /// `switched`: by a media key, the menu or Shortcuts, so the card shows which station is on.
    public func select(_ index: Int, switched: Bool = false) {
        guard stations.indices.contains(index) else { return }
        var changes: Change = switched ? .switched : []
        if index != current {
            current = index
            if active {
                startSession()
            } else {
                gaveUpOnNetworkAt = nil   // another station chosen: don't bring back the lost one
                status = .ready
                message = nil
                changes.insert(.state)
            }
        }
        emit(changes)
    }

    public func nextStation() {
        guard !stations.isEmpty else { return }
        select((current + 1) % stations.count, switched: true)
    }

    public func previousStation() {
        let count = stations.count
        guard count > 0 else { return }
        select(current >= 0 ? (current - 1 + count) % count : count - 1, switched: true)
    }

    // MARK: - Editing the station list

    private static func cleaned(_ s: Station) -> Station? {
        let name = s.name.trimmingCharacters(in: .whitespaces)
        let address = s.url.trimmingCharacters(in: .whitespaces)
        let logo = (s.logo ?? "").trimmingCharacters(in: .whitespaces)
        if name.isEmpty || !isWebURL(address) || (!logo.isEmpty && !isWebURL(logo)) { return nil }
        return Station(name: name, url: address, logo: logo.isEmpty ? nil : logo)
    }

    public func addStation(_ s: Station) -> AddResult {
        guard let station = Self.cleaned(s) else { return .invalid }
        if stations.contains(where: { sameStream($0.url, station.url) }) { return .duplicate }
        stations.append(station)
        if current < 0 { select(stations.count - 1) }
        stationsChanged()
        return .added
    }

    public func updateStation(_ index: Int, _ s: Station) -> AddResult {
        guard let station = Self.cleaned(s), stations.indices.contains(index) else { return .invalid }
        if stations.indices.contains(where: { $0 != index && sameStream(stations[$0].url, station.url) }) { return .duplicate }
        let old = stations[index]
        stations[index] = station
        if let last = prefs.lastPlayed, last == old.url {
            prefs.lastPlayed = station.url
            savePrefs()
        }
        if index == current && active && old.url != station.url {
            startSession()
        } else if current < 0 {
            select(index)
        }
        stationsChanged(index == current ? .state : [])
        return .added
    }

    /// Drag and drop: `to` is the insertion index before the removal (SwiftUI's onMove), so moving the first of
    /// three stations to 3 puts it last.
    public func moveStation(from: Int, to: Int) {
        let count = stations.count
        guard stations.indices.contains(from), (0...count).contains(to) else { return }
        let target = to > from ? to - 1 : to
        guard target != from else { return }
        let chosen = stations.indices.contains(current) ? stations[current] : nil
        let before = current
        stations.insert(stations.remove(at: from), at: target)
        if let chosen, let index = stations.firstIndex(of: chosen) { current = index }
        stationsChanged(current != before ? .state : [])
    }

    public func removeStation(_ index: Int) {
        guard stations.indices.contains(index) else { return }
        let removed = stations.remove(at: index)
        var changes: Change = []
        if index == current {
            current = -1
            stop()
        } else if index < current {
            current -= 1
            changes = .state
        }
        if prefs.lastPlayed == removed.url {
            prefs.lastPlayed = nil
            savePrefs()
        }
        stationsChanged(changes)
    }

    /// Adds the stations from a list exported here, on Windows or on Linux, skipping the ones already here.
    public func importStations(_ file: URL) -> ImportResult {
        guard let items = (try? readJSON(file)) as? [Any] else {
            return ImportResult(added: 0, error: L("This isn't a Minimalistic Radio station list."))
        }
        var known = Set(stations.map { streamKey($0.url) })
        var fresh: [Station] = []
        for case let item as [String: Any] in items {
            guard let name = item["Name"] as? String, !name.trimmingCharacters(in: .whitespaces).isEmpty,
                  let address = item["Url"] as? String, isWebURL(address) else { continue }
            let key = streamKey(address)
            if known.contains(key) { continue }
            known.insert(key)
            let logo = item["Logo"] as? String
            fresh.append(Station(name: name.trimmingCharacters(in: .whitespaces), url: address,
                                 logo: isWebURL(logo) ? logo : nil))
        }
        if !fresh.isEmpty {
            stations.append(contentsOf: fresh)
            stationsChanged()
        }
        return ImportResult(added: fresh.count, error: nil)
    }

    /// Writes the list the way Windows does. False if the file couldn't be saved.
    public func exportStations(_ file: URL) -> Bool {
        (try? saveStations(file, stations)) != nil
    }

    // MARK: - Preferences

    public func setLanguage(_ code: String) {
        guard supportedLanguageSettings.contains(code), code != prefs.language else { return }
        prefs.language = code
        savePrefs()
        emit(.preferences)
    }

    public func setShowStationPopup(_ on: Bool) {
        guard on != prefs.showStationPopup else { return }
        prefs.showStationPopup = on
        savePrefs()
        emit(.preferences)
    }

    public func setCheckUpdates(_ on: Bool) {
        guard on != prefs.checkUpdates else { return }
        prefs.checkUpdates = on
        savePrefs()
        emit(.preferences)
    }

    public func setLastUpdateCheck(_ date: Date) {
        prefs.lastUpdateCheck = date
        savePrefs()
    }

    public func setUpdateByDownload(_ on: Bool) {
        guard on != prefs.updateByDownload else { return }
        prefs.updateByDownload = on
        savePrefs()
        emit(.preferences)
    }
}
