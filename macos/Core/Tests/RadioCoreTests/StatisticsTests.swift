import Foundation
import Testing
@testable import RadioCore

// The Statistics page's numbers (docs/superpowers/specs/2026-11-15-ui-redesign-design.md, "How it is counted"):
// periods, sessions crossing their boundaries, the per-day average, the time format, the top lists, the titles share
// and the hours of the day. Everything in local time.

private let now = localDate(2026, 11, 15, 22, 0)

private func session(_ start: Date, _ minutes: Double, station: String = "Antyradio Hard",
                     url: String = "https://an05.cdn.eurozet.pl/ANTHAR.mp3", titles: Bool = true) -> ListeningSession {
    ListeningSession(station: station, url: url, start: start, end: start.addingTimeInterval(minutes * 60), titles: titles)
}

private func song(_ title: String, _ time: Date = localDate(2026, 11, 15, 20, 0), station: String = "Antyradio Hard") -> PlayedSong {
    PlayedSong(station: station, title: title, time: time)
}

private func summary(_ sessions: [ListeningSession], songs: [PlayedSong] = [], _ period: StatisticsPeriod = .month,
                     at time: Date = now) -> StatisticsSummary {
    summarizeStatistics(StatisticsLog(sessions: sessions, songs: songs), period: period, now: time)
}

// MARK: - Periods

@Test func monthCountsOnlyTheCurrentMonth() {
    let s = summary([session(localDate(2026, 11, 15, 19, 0), 90),
                     session(localDate(2026, 10, 20, 19, 0), 60),
                     session(localDate(2025, 11, 15, 19, 0), 30)])
    #expect(s.total == 90 * 60)
    #expect(s.start == localDate(2026, 11, 1, 0, 0))
}

@Test func yearCountsTheCurrentYearAndAllCountsEverything() {
    let sessions = [session(localDate(2026, 11, 15, 19, 0), 90),
                    session(localDate(2026, 1, 3, 19, 0), 60),
                    session(localDate(2025, 12, 31, 12, 0), 30)]
    #expect(summary(sessions, .year).total == 150 * 60)
    #expect(summary(sessions, .year).start == localDate(2026, 1, 1, 0, 0))
    #expect(summary(sessions, .all).total == 180 * 60)
    #expect(summary(sessions, .all).start == localDate(2025, 12, 31, 12, 0))
}

@Test func sessionCrossingTheMonthCountsOnlyItsPartInside() {
    // 31 October 23:00 → 1 November 01:00: one hour in each month.
    let crossing = session(localDate(2026, 10, 31, 23, 0), 120)
    #expect(summary([crossing], at: localDate(2026, 11, 2, 12, 0)).total == 60 * 60)
    #expect(summary([crossing], at: localDate(2026, 10, 31, 23, 30)).total == 60 * 60)
    #expect(summary([crossing], .all, at: localDate(2026, 11, 2, 12, 0)).total == 120 * 60)
}

@Test func sessionCrossingTheYearCountsOnlyItsPartInside() {
    // New Year's Eve 23:30 → 00:45.
    let crossing = session(localDate(2025, 12, 31, 23, 30), 75)
    let january = localDate(2026, 1, 1, 10, 0)
    #expect(summary([crossing], .year, at: january).total == 45 * 60)
    #expect(summary([crossing], .month, at: january).total == 45 * 60)
    #expect(summary([crossing], .year, at: localDate(2025, 12, 31, 23, 59)).total == 30 * 60)
}

@Test func longestSessionIsClippedToThePeriod() {
    let s = summary([session(localDate(2026, 10, 31, 22, 0), 180), session(localDate(2026, 11, 10, 18, 0), 70)],
                    at: localDate(2026, 11, 15, 12, 0))
    #expect(s.longest == 70 * 60)                                          // only 60 of the 180 minutes are in November
    #expect(summary([session(localDate(2026, 11, 10, 18, 0), 70), session(localDate(2026, 11, 11, 18, 0), 95)]).longest == 95 * 60)
}

@Test func nothingInThePeriodIsEmpty() {
    let s = summary([session(localDate(2026, 10, 20, 19, 0), 60)], songs: [song("A - B", localDate(2026, 10, 20, 19, 5))])
    #expect(s.isEmpty && s.total == 0 && s.songs == 0 && s.topStations.isEmpty && s.peakHour == nil)
    #expect(summary([]).isEmpty)
    #expect(!summary([session(localDate(2026, 11, 15, 19, 0), 1)]).isEmpty)
}

// MARK: - Per day

@Test func perDayDividesByTheDaysElapsedInThePeriod() {
    let sessions = [session(localDate(2026, 11, 15, 5, 0), 15 * 60)]      // 15 hours today
    #expect(summary(sessions, .month).perDay == 3600)                      // 15 November: 15 days
    let year = summary(sessions, .year)
    #expect(year.perDay == 54000 / 319.0)                                  // 15 November is day 319 of 2026
}

@Test func perDayForAllCountsTheDaysSinceTheFirstSession() {
    let today = session(localDate(2026, 11, 15, 10, 0), 60)
    #expect(summary([today], .all).perDay == 3600)                         // the first day: at least one day
    let earlier = session(localDate(2026, 11, 13, 23, 30), 60)             // two days ago, late in the evening
    #expect(summary([earlier, today], .all).perDay == 2400)                // the 13th, 14th and 15th
}

// MARK: - Time format

/// (hours, minutes, seconds) and the text.
private let durations: [(Int, Int, Int, String)] = [
    (0, 0, 0, "0 min"),
    (0, 18, 0, "18 min"),
    (0, 59, 20, "59 min"),
    (0, 59, 40, "1 h 00 min"),                                             // rounded to the nearest minute
    (42, 18, 0, "42 h 18 min"),
    (11, 5, 0, "11 h 05 min"),
    (99, 59, 0, "99 h 59 min"),
    (100, 0, 0, "100 h"),
    (386, 40, 0, "386 h"),
]

@Test func durationFormat() {
    for (hours, minutes, seconds, expected) in durations {
        let total = Double(hours * 3600 + minutes * 60 + seconds)
        #expect(formatDuration(total) == expected)
    }
}

@Test func durationFormatIsTranslated() {
    let polish: [String: String] = ["{0} min": "{0} min", "{0} h {1} min": "{0} godz. {1} min", "{0} h": "{0} godz."]
    let translate: (String) -> String = { polish[$0] ?? $0 }
    #expect(formatDuration(Double(2 * 3600 + 49 * 60), translate) == "2 godz. 49 min")
    #expect(formatDuration(Double(150 * 3600), translate) == "150 godz.")
}

// MARK: - Counts and top lists

@Test func songsAndStationsAreCountedInThePeriod() {
    let s = summary([session(localDate(2026, 11, 15, 19, 0), 60),
                     session(localDate(2026, 11, 14, 19, 0), 60, station: "Radio 357", url: "https://stream.radio357.pl/"),
                     session(localDate(2026, 11, 13, 19, 0), 60, station: "Radio 357", url: "https://stream.radio357.pl"),
                     session(localDate(2026, 10, 13, 19, 0), 60, station: "RMF FM", url: "http://rmf.example/live")],
                    songs: [song("Queen - A Kind Of Magic"), song("Dżingiel"), song("Old - Song", localDate(2026, 10, 13, 19, 5))])
    #expect(s.songs == 2)
    #expect(s.stations == 2)                                               // the same stream with or without a slash
}

@Test func topStationsByTimeUpToFive() {
    var sessions: [ListeningSession] = []
    for (index, minutes) in [30.0, 90, 60, 10, 45, 20].enumerated() {
        sessions.append(session(localDate(2026, 11, 10 + index, 18, 0), minutes, station: "S\(index)", url: "http://s\(index).example/live"))
    }
    sessions.append(session(localDate(2026, 11, 15, 8, 0), 30, station: "S0 renamed", url: "http://s0.example/live"))
    let top = summary(sessions).topStations
    #expect(top.map(\.name) == ["S1", "S0 renamed", "S2", "S4", "S5"])     // S0: 60 minutes in two sessions; ties by name
    #expect(top.map(\.time) == [5400, 3600, 3600, 2700, 1200])
    #expect(top[1].url == "http://s0.example/live")
}

@Test func topArtistsByPlaysUpToFive() {
    let titles = ["Queen - A Kind Of Magic", "Leonard Cohen - Everybody Knows", "QUEEN - Bohemian Rhapsody",
                  "Editors - Shadow", "Queen – Radio Ga Ga", "Leonard Cohen - Suzanne", "Daughtry - What About Now",
                  "Kult - Arahja", "Metallica - One", "Dżingiel", "Wiadomości", "AC/DC - Thunderstruck - Live"]
    let s = summary([session(localDate(2026, 11, 15, 19, 0), 60)], songs: titles.map { song($0) })
    #expect(s.topArtists.map(\.plays) == [3, 2, 1, 1, 1])
    #expect(s.topArtists[0].name.lowercased() == "queen")
    #expect(s.topArtists[1].name == "Leonard Cohen")
    #expect(s.topArtists.map(\.name)[2...] == ["AC/DC", "Daughtry", "Editors"])   // ties: by name
    #expect(s.songs == 12)                                                 // titles without an artist still count
}

@Test(arguments: [
    ("Queen - A Kind Of Magic", "Queen"),
    ("Sienna Spiro – Great Expectation", "Sienna Spiro"),
    ("AC/DC - Thunderstruck - Live", "AC/DC"),
    ("Dżingiel", nil),
    (" - Untitled", nil),
] as [(String, String?)])
func artistIsThePartBeforeTheFirstDash(title: String, artist: String?) {
    #expect(artistOf(title) == artist)
}

// MARK: - Titles share

@Test func titlesShareIsTheTimeOfSessionsWithTitles() {
    let s = summary([session(localDate(2026, 11, 15, 19, 0), 58, titles: true),
                     session(localDate(2026, 11, 14, 19, 0), 42, titles: false)], songs: [song("Queen - A Kind Of Magic")])
    #expect(abs(s.titlesShare - 0.58) < 1e-9)
    #expect(s.showsArtists)
}

@Test func artistsNeedATitlesShareOfAtLeast20Percent() {
    let songs = [song("Queen - A Kind Of Magic")]
    let below = summary([session(localDate(2026, 11, 15, 19, 0), 19, titles: true),
                         session(localDate(2026, 11, 14, 19, 0), 81, titles: false)], songs: songs)
    #expect(!below.showsArtists)
    let at = summary([session(localDate(2026, 11, 15, 19, 0), 20, titles: true),
                      session(localDate(2026, 11, 14, 19, 0), 80, titles: false)], songs: songs)
    #expect(at.showsArtists)
    let noArtists = summary([session(localDate(2026, 11, 15, 19, 0), 60, titles: true)], songs: [song("Dżingiel")])
    #expect(!noArtists.showsArtists)                                       // titles, but none with an artist
}

// MARK: - Hours of the day

@Test func hoursSplitSessionsByTheHour() {
    let s = summary([session(localDate(2026, 11, 15, 19, 30), 105)])       // 19:30 → 21:15
    #expect(s.hours.count == 24)
    #expect(Array(s.hours[19...21]) == [1800, 3600, 900])
    #expect(s.hours.reduce(0, +) == 105 * 60)
    #expect(s.peakHour == 20)
}

@Test func hoursCrossMidnightAndAddUp() {
    let s = summary([session(localDate(2026, 11, 13, 23, 30), 60),         // 23:30 → 00:30
                     session(localDate(2026, 11, 14, 0, 10), 10)])
    #expect(s.hours[23] == 1800)
    #expect(s.hours[0] == 2400)
    #expect(s.peakHour == 0)
}

@Test func hoursCountOnlyThePartInThePeriod() {
    let s = summary([session(localDate(2026, 10, 31, 23, 30), 60)], at: localDate(2026, 11, 15, 12, 0))
    #expect(s.hours[23] == 0)
    #expect(s.hours[0] == 1800)
}

@Test func peakHourTiesGoToTheEarlierHour() {
    let s = summary([session(localDate(2026, 11, 15, 8, 0), 60), session(localDate(2026, 11, 15, 20, 0), 60)])
    #expect(s.peakHour == 8)
}

// MARK: - statistics.json

@Test func statisticsRoundTripInUTC() throws {
    let f = tempFolder().appendingPathComponent("statistics.json")
    let log = StatisticsLog(sessions: [ListeningSession(station: "Antyradio Hard", url: "https://an05.cdn.eurozet.pl/ANTHAR.mp3",
                                                         start: localDate(2026, 11, 15, 19, 2), end: localDate(2026, 11, 15, 20, 41, 30),
                                                         titles: true)],
                            songs: [PlayedSong(station: "Antyradio Hard", title: "Leonard Cohen - Everybody Knows",
                                               time: localDate(2026, 11, 15, 19, 5, 12))])
    try saveStatistics(f, log)
    #expect(loadStatistics(f) == log)
    let json = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: f)) as? [String: Any])
    #expect(json["version"] as? Int == 1)
    let saved = try #require((json["sessions"] as? [[String: Any]])?.first)
    #expect(Set(saved.keys) == ["station", "url", "start", "end", "titles"])
    #expect((saved["start"] as? String)?.hasSuffix("Z") == true)
    #expect(ISO8601DateFormatter().date(from: saved["start"] as? String ?? "") == localDate(2026, 11, 15, 19, 2))
    let songs = try #require(json["songs"] as? [[String: Any]])
    #expect(Set(songs[0].keys) == ["station", "title", "time"])
}

@Test func statisticsSkipBadEntriesAndMoveACorruptFileAside() throws {
    let folder = tempFolder()
    let f = folder.appendingPathComponent("statistics.json")
    #expect(loadStatistics(f) == StatisticsLog())
    try Data(#"{"version": 1, "sessions": [{"station": "A", "url": "http://a/1", "start": "2026-11-15T19:00:00Z", "end": "2026-11-15T19:30:00Z", "titles": false}, {"station": "B"}, {"station": "C", "url": "http://c/1", "start": "2026-11-15T19:00:00Z", "end": "2026-11-15T18:00:00Z", "titles": true}], "songs": [{"title": 5}]}"#.utf8).write(to: f)
    let loaded = loadStatistics(f)
    #expect(loaded.sessions.map(\.station) == ["A"] && loaded.songs.isEmpty)
    try Data("{oops".utf8).write(to: f)
    #expect(loadStatistics(f) == StatisticsLog())
    #expect(try String(contentsOf: folder.appendingPathComponent("statistics.json.bad"), encoding: .utf8) == "{oops")
}
