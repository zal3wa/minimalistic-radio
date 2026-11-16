import CryptoKit
import Foundation

// The radio itself: what plays, reconnecting, the sleep timer, song history, the listening statistics and the
// station list.
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
let logosKept = 200                                     // pictures kept in the logo cache
let volumeBurst: TimeInterval = 1                       // volume changes closer than this are one (a drag, keys)
let switchSettle: Double = 0.3                          // a media key or menu switch connects once switching pauses
let sessionRejoin: TimeInterval = 2 * 60                // a reconnect this soon continues the listening session
let statisticsSaveSeconds: Double = 5 * 60              // a running session is saved this often

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
    /// The statistics were cleared.
    public static let statistics = Change(rawValue: 1 << 10)
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
    /// Listening sessions and songs (statistics.json). A running session's end is updated every 5 minutes;
    /// `statisticsNow` has it up to now.
    public private(set) var statistics = StatisticsLog()
    public private(set) var corruptStations = false
    /// Set when the retries ran out on network errors: networkAvailable() starts again within 10 minutes.
    public private(set) var gaveUpOnNetworkAt: Date?

    // Saving, replaceable in tests.
    var writeStations: (URL, [Station]) throws -> Void = saveStations
    var writePreferences: (URL, Preferences) throws -> Void = savePreferences
    var writeHistory: (URL, [HistoryEntry]) throws -> Void = saveHistory
    var writeStatistics: (URL, StatisticsLog) throws -> Void = saveStatistics

    private var listeners: [Int: (Change) -> Void] = [:]
    private var nextListener = 0
    private let covers = CoverCache()
    private var fade = 100
    private var sleepTimer: AnyObject?
    // Muting: unmute goes back to the level from before the last burst of changes (see setVolume).
    private var unmuteVolume = Preferences().volume
    private var volumeBefore = Preferences().volume
    private var volumeChangedAt: Date?
    // The playback session: one per play(), until stop() or the next play().
    private var session = 0
    private var url = ""
    private var kind = "generic"
    private var attempt = 0
    private var everPlayed = false
    private var attemptStarted = Date.distantPast
    private var retryTimer: AnyObject?
    private var pollTimer: AnyObject?
    private var switchTimer: AnyObject?   // set while a switched station waits to connect
    private var polling = false
    // Statistics: the last of statistics.sessions is running while audio plays.
    private var listening = false
    private var statisticsTimer: AnyObject?

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
        statistics = loadStatistics(paths.statisticsFile)
        volume = prefs.volume
        pruneFolder(paths.coversFolder, keep: coversKept)
        pruneFolder(paths.logosFolder, keep: logosKept)
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

    private func saveStatisticsFile() {
        try? writeStatistics(paths.statisticsFile, statistics)
    }

    // MARK: - Playback

    /// Starts the chosen station (the first one if none is chosen). A station already on keeps going.
    /// False when there is nothing to play (no stations yet).
    @discardableResult
    public func play() -> Bool {
        guard !stations.isEmpty else { return false }
        if !active { startSession() }
        return true
    }

    /// A new connection to the chosen station, dropping the current one (StartPlayback on Windows).
    func startSession() {
        guard !stations.isEmpty else { return }
        if !stations.indices.contains(current) { current = 0 }
        endSession()
        url = stations[current].url
        kind = stationKind(url)
        attempt = 0
        everPlayed = false
        polling = false
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
        listeningStopped()
        session += 1
        for timer in [retryTimer, pollTimer, switchTimer].compactMap({ $0 }) { scheduler.cancel(timer) }
        retryTimer = nil
        pollTimer = nil
        switchTimer = nil
        gaveUpOnNetworkAt = nil
        track = nil
        coverPath = nil
    }

    private func connect() {
        retryTimer = nil
        status = .connecting
        message = nil
        attemptStarted = scheduler.now()
        player.play(url)
    }

    private func retry(_ wanted: Int) {
        guard wanted == session, status == .retrying else { return }
        connect()
        emit(.state)
    }

    /// The stream broke (`error`) or simply ended (nil). Mirrors the retry loop of StartPlayback on Windows.
    private func connectionEnded(_ error: String?) {
        let now = scheduler.now()
        if now.timeIntervalSince(attemptStarted) > longConnection { attempt = 0 }
        if attempt >= (everPlayed ? retriesOncePlayed : retriesNeverPlayed) {
            if let error {
                stop(message: error)
                gaveUpOnNetworkAt = now
            } else {
                stop(message: L("The broadcast has ended"))
            }
            return
        }
        let delay = backoff[min(attempt, backoff.count - 1)]
        attempt += 1
        listeningStopped()
        player.stop()
        track = nil
        coverPath = nil
        status = .retrying
        message = L("Connection lost. Retrying in {0} s…").replacingOccurrences(of: "{0}", with: String(Int(delay)))
        let wanted = session
        retryTimer = scheduler.callLater(delay) { [weak self] in self?.retry(wanted) }
        emit([.state, .track, .cover])
    }

    /// The network settled: connect now instead of waiting out a retry, or start again if the retries ran out
    /// because the connection was lost less than 10 minutes ago. A playing station kept its connection (a VPN, a new
    /// interface), unless the network was down in between.
    public func networkAvailable(wasDown: Bool = true) {
        if status == .playing && !wasDown { return }
        comeBack()
    }

    /// Back from sleep: the old connection is dead.
    public func resumed() {
        comeBack()
    }

    private func comeBack() {
        if active { startSession(); return }
        if let lost = gaveUpOnNetworkAt, scheduler.now().timeIntervalSince(lost) < networkReturnWindow { startSession() }
    }

    // MARK: - Called by the player (on the main thread)

    /// While a switch waits to connect, the player still plays the station from before: not this one's news.
    private func connected() -> Bool {
        switchTimer == nil && (status == .connecting || status == .playing)
    }

    public func onPlayerStarted() {
        guard status == .connecting, switchTimer == nil else { return }
        everPlayed = true
        status = .playing
        message = nil
        prefs.lastPlayed = url
        savePrefs()
        listeningStarted()
        emit(.state)
        if kind == "radio357" && !polling {
            polling = true
            pollRadio357(session)
        }
    }

    public func onPlayerTitle(_ raw: String) {
        // Radio 357 sends a fixed slogan in the stream; its songs come from playing.json.
        if connected() && kind != "radio357" { showTrack(raw) }
    }

    public func onPlayerError(_ kind: ErrorKind, detail: String) {
        guard connected() else { return }
        if kind == .network { connectionEnded(detail) } else { stop(message: detail) }
    }

    public func onPlayerEOS() {
        if connected() { connectionEnded(nil) }
    }

    // MARK: - Titles, covers, history

    private func showTrack(_ raw: String?) {
        let title = parseTitle(raw, kind: kind)
        let artwork = title != nil ? artworkFromRaw(raw) : nil
        if title == track { return }
        track = title
        coverPath = nil
        if title != nil && listening { statistics.sessions[statistics.sessions.count - 1].titles = true }
        var changes: Change = [.track, .cover]
        if let title, addToHistory(title) { changes.insert(.history) }
        emit(changes)
        guard let title else { return }
        if let artwork { downloadCover(artwork, title) } else { findCover(title) }
    }

    private func stillShowing(_ wanted: Int, _ title: String) -> Bool {
        wanted == session && track == title
    }

    private func findCover(_ title: String) {
        let known = covers.get(title)
        if known.known {
            if let url = known.url { downloadCover(url, title) }
            return
        }
        guard let search = itunesSearchURL(title) else { return }
        let wanted = session
        fetch(search) { [weak self] payload in
            guard let self, let payload else { return }   // a failed lookup isn't remembered: asked again next time
            let cover = pickCover(artist: splitTrack(title).artist ?? "", payload: payload)
            self.covers.put(title, cover)
            if let cover, self.stillShowing(wanted, title) { self.downloadCover(cover, title) }
        }
    }

    private func downloadCover(_ address: String, _ title: String) {
        guard let source = URL(string: address) else { return }
        let hex = Insecure.SHA1.hash(data: Data(address.utf8)).map { String(format: "%02x", $0) }.joined()
        let file = paths.coversFolder.appendingPathComponent(hex + ".jpg")
        if FileManager.default.fileExists(atPath: file.path) {
            showCover(file)
            return
        }
        guard (try? FileManager.default.createDirectory(at: paths.coversFolder, withIntermediateDirectories: true)) != nil else { return }
        let wanted = session
        fetchFile(source, file) { [weak self] ok in
            guard let self, ok, self.stillShowing(wanted, title) else { return }
            self.showCover(file)
        }
    }

    private func showCover(_ file: URL) {
        coverPath = file
        emit(.cover)
    }

    /// Every 10 s after each answer, while this session lasts.
    private func pollRadio357(_ wanted: Int) {
        pollTimer = nil
        guard wanted == session else { return }
        fetch(radio357URL) { [weak self] payload in
            guard let self, wanted == self.session else { return }
            if self.connected() { self.showTrack(radio357Title(payload)) }
            self.pollTimer = self.scheduler.callLater(radio357PollSeconds) { [weak self] in self?.pollRadio357(wanted) }
        }
    }

    private func addToHistory(_ title: String) -> Bool {
        let station = stationName ?? appName
        if let first = history.first, first.title == title, first.station == station { return false }
        history.insert(HistoryEntry(title: title, station: station, time: scheduler.now()), at: 0)
        if history.count > historyLimit { history.removeLast(history.count - historyLimit) }
        saveHistoryFile()
        if prefs.collectStatistics {
            statistics.songs.append(PlayedSong(station: station, title: title, time: scheduler.now()))   // saved with the session
        }
        return true
    }

    public func clearHistory() {
        history.removeAll()
        saveHistoryFile()
        emit(.history)
    }

    // MARK: - Statistics

    /// Audio started: continues the last session if this station was playing less than 2 minutes ago (a reconnect),
    /// otherwise starts a new one. Nothing while the statistics are switched off.
    private func listeningStarted() {
        guard prefs.collectStatistics, !listening, stations.indices.contains(current) else { return }
        let now = scheduler.now()
        if let last = statistics.sessions.last, sameStream(last.url, url), now.timeIntervalSince(last.end) <= sessionRejoin {
            statistics.sessions[statistics.sessions.count - 1].end = max(last.end, now)
        } else {
            statistics.sessions.append(ListeningSession(station: stations[current].name, url: url, start: now, end: now,
                                                        titles: false))
        }
        if track != nil { statistics.sessions[statistics.sessions.count - 1].titles = true }
        listening = true
        scheduleStatisticsSave()
    }

    /// While audio plays, the session is saved every 5 minutes: a crash loses at most that much.
    private func scheduleStatisticsSave() {
        statisticsTimer = scheduler.callLater(statisticsSaveSeconds) { [weak self] in
            guard let self, self.listening else { return }
            self.statistics.sessions[self.statistics.sessions.count - 1].end = self.scheduler.now()
            self.saveStatisticsFile()
            self.scheduleStatisticsSave()
        }
    }

    /// Audio stopped: the running session ends now (and is dropped if no time passed).
    private func listeningStopped() {
        guard listening else { return }
        listening = false
        if let timer = statisticsTimer { scheduler.cancel(timer) }
        statisticsTimer = nil
        let index = statistics.sessions.count - 1
        statistics.sessions[index].end = max(statistics.sessions[index].end, scheduler.now())
        if statistics.sessions[index].end <= statistics.sessions[index].start { statistics.sessions.remove(at: index) }
        saveStatisticsFile()
    }

    /// The statistics with the running session counted up to now, for the Statistics page.
    public var statisticsNow: StatisticsLog {
        var log = statistics
        if listening, let index = log.sessions.indices.last {
            log.sessions[index].end = max(log.sessions[index].end, scheduler.now())
        }
        return log
    }

    /// Deletes the statistics (not the song history). A station playing now counts on from here.
    public func clearStatistics() {
        let wasListening = listening
        if let timer = statisticsTimer { scheduler.cancel(timer) }
        statisticsTimer = nil
        listening = false
        statistics = StatisticsLog()
        saveStatisticsFile()
        if wasListening && status == .playing { listeningStarted() }
        emit(.statistics)
    }

    /// The Mac goes to sleep: the session ends here, so the night doesn't count. Waking up connects again.
    public func willSleep() {
        listeningStopped()
    }

    /// The app quits: the running session and the songs are saved.
    public func willQuit() {
        if listening { listeningStopped() } else { saveStatisticsFile() }
    }

    // MARK: - Volume and sleep timer

    public func setVolume(_ percent: Int) {
        let value = max(0, min(100, percent))
        guard value != volume else { return }
        // Changes less than a second apart count as one (as on Windows): turned down to 0 that way,
        // unmuting brings back the level from before them, not the 1 % passed last.
        let now = scheduler.now()
        if volumeChangedAt.map({ now.timeIntervalSince($0) > volumeBurst }) ?? true { volumeBefore = volume }
        volumeChangedAt = now
        if value == 0 && volumeBefore > 0 { unmuteVolume = volumeBefore }
        volume = value
        prefs.volume = value
        player.setVolume(effectiveVolume)
        savePrefs()
        emit(.volume)
    }

    /// The speaker button: mutes, or unmutes to the level from before (30 if there was none).
    public func toggleMute() {
        let before = volume
        setVolume(before == 0 ? unmuteVolume : 0)
        if before > 0 { unmuteVolume = before }
    }

    public func setSleepTimer(minutes: Int?) {
        if let timer = sleepTimer {
            scheduler.cancel(timer)
            sleepTimer = nil
        }
        let minutes = (minutes ?? 0) > 0 ? minutes : nil
        sleepMinutes = minutes
        sleepAt = minutes.map { scheduler.now().addingTimeInterval(Double($0) * 60) }
        setFade(100)
        if minutes != nil {
            sleepTimer = scheduler.callLater(1) { [weak self] in self?.sleepTick() }
        }
        emit(.sleep)
    }

    private func sleepTick() {
        sleepTimer = nil
        guard let sleepAt else { return }
        let left = sleepAt.timeIntervalSince(scheduler.now())
        if left <= 0 {
            if active {
                stop(message: L("Stopped by the sleep timer"))
            } else {
                gaveUpOnNetworkAt = nil   // the network coming back must not start it again
            }
            setSleepTimer(minutes: nil)   // after stopping, so the full volume never sounds
            return
        }
        setFade(left >= fadeSeconds ? 100 : Int(left * 100 / fadeSeconds))
        sleepTimer = scheduler.callLater(1) { [weak self] in self?.sleepTick() }
    }

    private func setFade(_ value: Int) {
        guard value != fade else { return }
        fade = value
        player.setVolume(effectiveVolume)
    }

    // MARK: - Choosing a station

    /// `switched`: by a media key, the menu or Shortcuts, so the card shows which station is on.
    public func select(_ index: Int, switched: Bool = false) {
        guard stations.indices.contains(index) else { return }
        var changes: Change = switched ? .switched : []
        if index != current {
            current = index
            if active && switched {
                // Shows the new station at once, but connects only after a pause in switching: skipping through
                // stations doesn't connect to each one.
                endSession()   // also drops a switch still waiting
                status = .connecting
                message = nil
                switchTimer = scheduler.callLater(switchSettle) { [weak self] in
                    self?.switchTimer = nil
                    self?.startSession()
                }
                changes.formUnion([.state, .track, .cover])
            } else if active {
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

    /// The form, radio-browser and share links all add through here: the name cleaned, the addresses checked.
    private static func cleaned(_ s: Station) -> Station? {
        let name = cleanName(s.name)
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

    // MARK: - Shared stations

    /// A share link for a station already on the list (the link's matching): plays it, true. Otherwise false, and
    /// the panel asks first.
    public func playIfKnown(_ shared: SharedStation) -> Bool {
        guard let index = stations.firstIndex(where: { sameStationAddress($0.url, shared.url) }) else { return false }
        select(index)
        play()
        return true
    }

    /// Shared station › Add and play: the station at the end of the list, playing. If the list already has the
    /// stream under a slightly different address (http instead of https), that one plays.
    @discardableResult
    public func addAndPlay(_ shared: SharedStation) -> Bool {
        let station = Station(name: shared.name, url: shared.url, logo: shared.logo)
        switch addStation(station) {
        case .added:
            select(stations.count - 1)
        case .duplicate:
            guard let index = stations.firstIndex(where: { sameStream($0.url, station.url) }) else { return false }
            select(index)
        case .invalid:
            return false
        }
        play()
        return true
    }

    /// Adds the stations from a list exported here, on Windows or on Linux, skipping the ones already here.
    public func importStations(_ file: URL) -> ImportResult {
        guard let items = (try? readJSON(file)) as? [Any] else {
            return ImportResult(added: 0, error: L("This isn't a Minimalistic Radio station list."))
        }
        var known = Set(stations.map { streamKey($0.url) })
        var fresh: [Station] = []
        for case let item as [String: Any] in items {
            let name = cleanName(item["Name"] as? String)
            guard !name.isEmpty, let address = item["Url"] as? String, isWebURL(address) else { continue }
            let key = streamKey(address)
            if known.contains(key) { continue }
            known.insert(key)
            let logo = item["Logo"] as? String
            fresh.append(Station(name: name, url: address, logo: isWebURL(logo) ? logo : nil))
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

    /// Settings › Statistics. Off ends the running session (what was collected stays); on counts the station
    /// playing now from here.
    public func setCollectStatistics(_ on: Bool) {
        guard on != prefs.collectStatistics else { return }
        prefs.collectStatistics = on
        savePrefs()
        if on {
            if status == .playing { listeningStarted() }
        } else {
            listeningStopped()
        }
        emit(.preferences)
    }
}
