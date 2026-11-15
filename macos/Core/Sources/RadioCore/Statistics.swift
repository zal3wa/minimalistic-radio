import Foundation

// Listening statistics: what statistics.json holds, and the numbers of the Statistics page. Kept only on this
// computer. The rules are in docs/superpowers/specs/2026-11-15-ui-redesign-design.md ("How it is counted").

/// Time actually spent listening to one station: from the start of audio to Stop, a station change, the sleep timer,
/// an error that stops playback or quitting. `titles`: the station sent at least one song title meanwhile.
public struct ListeningSession: Equatable, Sendable {
    public var station: String
    public var url: String
    public var start: Date
    public var end: Date
    public var titles: Bool

    public init(station: String, url: String, start: Date, end: Date, titles: Bool) {
        self.station = station
        self.url = url
        self.start = start
        self.end = end
        self.titles = titles
    }
}

/// A song as the history got it (same filters: no ads, station names or repeats).
public struct PlayedSong: Equatable, Sendable {
    public var station: String
    public var title: String
    public var time: Date

    public init(station: String, title: String, time: Date) {
        self.station = station
        self.title = title
        self.time = time
    }
}

/// statistics.json: {"version": 1, "sessions": [...], "songs": [...]}, times in UTC ("2026-11-15T19:02:00Z").
public struct StatisticsLog: Equatable, Sendable {
    public var sessions: [ListeningSession]
    public var songs: [PlayedSong]

    public init(sessions: [ListeningSession] = [], songs: [PlayedSong] = []) {
        self.sessions = sessions
        self.songs = songs
    }
}

public enum StatisticsPeriod: String, CaseIterable, Sendable {
    case all, year, month
}

/// Top artists show only when sessions with song titles make up at least this share of the listening time.
public let artistsShareThreshold = 0.2
let topCount = 5

public struct StationTime: Equatable, Sendable {
    public let name: String
    public let url: String
    public let time: TimeInterval
}

public struct ArtistPlays: Equatable, Sendable {
    public let name: String
    public let plays: Int
}

/// The Statistics page for one period. Times are in seconds.
public struct StatisticsSummary: Equatable, Sendable {
    /// Where the period starts: the 1st of the month, 1 January, or (All) the first thing recorded.
    public var start: Date?
    public var total: TimeInterval = 0
    public var perDay: TimeInterval = 0
    /// Song titles received.
    public var songs = 0
    /// Stations listened to.
    public var stations = 0
    /// The longest single session (its part inside the period).
    public var longest: TimeInterval = 0
    public var topStations: [StationTime] = []
    /// Listening time of sessions with song titles, as a share of all listening time (0…1).
    public var titlesShare: Double = 0
    public var topArtists: [ArtistPlays] = []
    /// Listening time in each hour of the day, 00 to 23.
    public var hours = [TimeInterval](repeating: 0, count: 24)

    public var isEmpty: Bool { total <= 0 && songs == 0 }

    public var showsArtists: Bool { titlesShare >= artistsShareThreshold && !topArtists.isEmpty }

    /// The hour most listened to (the earlier one on a tie), nil with no listening.
    public var peakHour: Int? {
        guard let most = hours.max(), most > 0 else { return nil }
        return hours.firstIndex(of: most)
    }
}

/// The period's sessions and songs counted as the spec says: local time, sessions cut at the period's edges.
public func summarizeStatistics(_ log: StatisticsLog, period: StatisticsPeriod, now: Date,
                                calendar: Calendar = .current) -> StatisticsSummary {
    let range: DateInterval?
    switch period {
    case .all: range = nil
    case .year: range = calendar.dateInterval(of: .year, for: now)
    case .month: range = calendar.dateInterval(of: .month, for: now)
    }
    func inside(_ start: Date, _ end: Date) -> (Date, Date)? {
        let from = max(start, range?.start ?? start), to = min(end, range?.end ?? end)
        return to > from ? (from, to) : nil
    }

    var summary = StatisticsSummary()
    var titled: TimeInterval = 0
    var byStation: [String: (name: String, url: String, latest: Date, time: TimeInterval)] = [:]
    for session in log.sessions {
        guard let (from, to) = inside(session.start, session.end) else { continue }
        let time = to.timeIntervalSince(from)
        summary.total += time
        summary.longest = max(summary.longest, time)
        if session.titles { titled += time }
        let key = streamKey(session.url)
        var entry = byStation[key] ?? (session.station, session.url, session.start, 0)
        if session.start >= entry.latest { (entry.name, entry.url, entry.latest) = (session.station, session.url, session.start) }
        entry.time += time
        byStation[key] = entry
        var hour = from
        while hour < to {
            let next = min(calendar.dateInterval(of: .hour, for: hour)?.end ?? to, to)
            summary.hours[calendar.component(.hour, from: hour)] += next.timeIntervalSince(hour)
            hour = next
        }
    }
    summary.stations = byStation.count
    summary.topStations = byStation.values
        .sorted { ($0.time, $1.name.lowercased()) > ($1.time, $0.name.lowercased()) }
        .prefix(topCount)
        .map { StationTime(name: $0.name, url: $0.url, time: $0.time) }
    summary.titlesShare = summary.total > 0 ? titled / summary.total : 0

    var artists: [String: (name: String, plays: Int)] = [:]
    for song in log.songs where range.map({ song.time >= $0.start && song.time < $0.end }) ?? true {
        summary.songs += 1
        guard let artist = artistOf(song.title) else { continue }
        let key = artist.lowercased()
        artists[key] = (artist, (artists[key]?.plays ?? 0) + 1)
    }
    summary.topArtists = artists.values
        .sorted { ($0.plays, $1.name.lowercased()) > ($1.plays, $0.name.lowercased()) }
        .prefix(topCount)
        .map { ArtistPlays(name: $0.name, plays: $0.plays) }

    let first = (log.sessions.map(\.start) + log.songs.map(\.time)).min()
    summary.start = range?.start ?? first
    let days: Int
    switch period {
    case .month: days = calendar.component(.day, from: now)
    case .year: days = calendar.ordinality(of: .day, in: .year, for: now) ?? 1
    case .all:
        days = first.flatMap {
            calendar.dateComponents([.day], from: calendar.startOfDay(for: $0), to: calendar.startOfDay(for: now)).day
        }.map { $0 + 1 } ?? 1
    }
    summary.perDay = summary.total / Double(max(1, days))
    return summary
}

/// The artist: the part of a song title before the first " - " (or the en or em dash some stations use).
func artistOf(_ title: String) -> String? {
    let separators = [" - ", " – ", " — "].compactMap { title.range(of: $0) }
    guard let first = separators.min(by: { $0.lowerBound < $1.lowerBound }) else { return nil }
    let artist = title[..<first.lowerBound].trimmingCharacters(in: .whitespaces)
    return artist.isEmpty ? nil : artist
}

/// Listening time: "18 min" under an hour, "42 h 18 min" under 100 hours, then "386 h". Rounded to the minute.
/// `L` translates the three forms.
public func formatDuration(_ seconds: TimeInterval, _ L: (String) -> String = { $0 }) -> String {
    let minutes = max(0, Int((seconds / 60).rounded()))
    if minutes < 60 {
        return L("{0} min").replacingOccurrences(of: "{0}", with: String(minutes))
    }
    let hours = minutes / 60
    if hours < 100 {
        return L("{0} h {1} min").replacingOccurrences(of: "{0}", with: String(hours))
            .replacingOccurrences(of: "{1}", with: String(format: "%02d", minutes % 60))
    }
    return L("{0} h").replacingOccurrences(of: "{0}", with: String(hours))
}

// MARK: - statistics.json

private func utcFormatter() -> ISO8601DateFormatter {
    ISO8601DateFormatter()   // "2026-11-15T19:02:00Z"
}

private func parseStatisticsTime(_ value: Any?) -> Date? {
    guard let text = value as? String else { return nil }
    return utcFormatter().date(from: text) ?? parseTime(text)
}

/// The statistics; empty when the file is missing. A file that can't be read is moved aside (statistics.json.bad),
/// so new statistics don't overwrite it.
public func loadStatistics(_ url: URL) -> StatisticsLog {
    let data: Any?
    do {
        data = try readJSON(url)
    } catch {
        moveAside(url)
        return StatisticsLog()
    }
    guard let data else { return StatisticsLog() }
    guard let object = data as? [String: Any] else {
        moveAside(url)
        return StatisticsLog()
    }
    var log = StatisticsLog()
    for case let item as [String: Any] in object["sessions"] as? [Any] ?? [] {
        guard let station = item["station"] as? String, let start = parseStatisticsTime(item["start"]),
              let end = parseStatisticsTime(item["end"]), end >= start else { continue }
        let titles = (item["titles"] as? NSNumber).map { isBool($0) && $0.boolValue } ?? false
        log.sessions.append(ListeningSession(station: station, url: item["url"] as? String ?? "", start: start, end: end,
                                             titles: titles))
    }
    for case let item as [String: Any] in object["songs"] as? [Any] ?? [] {
        guard let title = item["title"] as? String, let time = parseStatisticsTime(item["time"]) else { continue }
        log.songs.append(PlayedSong(station: item["station"] as? String ?? "", title: title, time: time))
    }
    return log
}

public func saveStatistics(_ url: URL, _ log: StatisticsLog) throws {
    let format = utcFormatter()
    let data: [String: Any] = [
        "version": 1,
        "sessions": log.sessions.map { session -> [String: Any] in
            ["station": session.station, "url": session.url, "start": format.string(from: session.start),
             "end": format.string(from: session.end), "titles": session.titles]
        },
        "songs": log.songs.map { song -> [String: Any] in
            ["station": song.station, "title": song.title, "time": format.string(from: song.time)]
        },
    ]
    try writeJSON(url, data)
}
