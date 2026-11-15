import Foundation
import Testing
@testable import RadioCore

// Recording listening sessions and songs into statistics.json (the spec's "What is recorded").

@MainActor private func saved(_ r: Rig) -> StatisticsLog {
    loadStatistics(r.paths.statisticsFile)
}

@MainActor private func at(_ r: Rig, _ seconds: Double) -> Date {
    r.scheduler.start.addingTimeInterval(seconds)
}

@MainActor @Test func sessionRunsFromTheStartOfAudioToStop() {
    let r = Rig.started(), c = r.controller
    c.select(0)
    c.play()
    r.scheduler.advance(3)                                                 // connecting: not listening yet
    c.onPlayerStarted()
    r.scheduler.advance(10 * 60)
    c.stop()
    #expect(saved(r).sessions == [ListeningSession(station: A.name, url: A.url, start: at(r, 3), end: at(r, 603), titles: false)])
    #expect(c.statistics == saved(r))
}

@MainActor @Test func nothingIsRecordedWithoutAudio() {
    let r = Rig.started(), c = r.controller
    c.select(0)
    c.play()
    r.scheduler.advance(5)
    c.onPlayerError(.refused, detail: "403 Forbidden")
    #expect(c.statistics.sessions.isEmpty)
    playing(c)
    c.stop()                                                               // no time passed: nothing to count
    #expect(c.statistics.sessions.isEmpty)
}

@MainActor @Test func reconnectWithinTwoMinutesContinuesTheSession() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(20 * 60)
    c.onPlayerError(.network, detail: "lost")                              // t = 20 min: the connection drops
    r.scheduler.advance(2)
    c.onPlayerStarted()                                                    // back 2 s later
    r.scheduler.advance(10 * 60)
    c.stop()
    #expect(saved(r).sessions.count == 1)
    #expect(saved(r).sessions.first?.start == at(r, 0) && saved(r).sessions.first?.end == at(r, 30 * 60 + 2))
}

@MainActor @Test func reconnectAfterMoreThanTwoMinutesStartsANewSession() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(10 * 60)
    c.stop()
    r.scheduler.advance(2 * 60 + 1)
    playing(c)
    r.scheduler.advance(60)
    c.stop()
    #expect(saved(r).sessions.map(\.start) == [at(r, 0), at(r, 12 * 60 + 1)])
}

@MainActor @Test func stationChangeEndsTheSession() {
    let r = Rig.started(), c = r.controller
    playing(c, 0)
    r.scheduler.advance(60)
    c.select(1)                                                            // switches while playing
    #expect(c.statistics.sessions.map(\.end) == [at(r, 60)])
    r.scheduler.advance(1)
    c.onPlayerStarted()
    r.scheduler.advance(60)
    c.stop()
    #expect(saved(r).sessions.map(\.url) == [A.url, B.url])
    #expect(saved(r).sessions.map(\.station) == [A.name, B.name])
}

@MainActor @Test func sleepTimerEndsTheSession() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.setSleepTimer(minutes: 15)
    r.scheduler.advance(15 * 60)
    #expect(c.status == .stopped && saved(r).sessions.first?.end == at(r, 15 * 60))
}

@MainActor @Test func runningSessionIsSavedEveryFiveMinutes() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(4 * 60)
    #expect(saved(r).sessions.isEmpty)
    r.scheduler.advance(60)
    #expect(saved(r).sessions.first?.end == at(r, 5 * 60))
    r.scheduler.advance(5 * 60)
    #expect(saved(r).sessions.first?.end == at(r, 10 * 60))
    c.stop()
    r.scheduler.advance(30 * 60)
    #expect(saved(r).sessions.first?.end == at(r, 10 * 60) && r.scheduler.pending == 0)
}

@MainActor @Test func statisticsNowCountsTheRunningSessionUpToNow() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(90)
    #expect(c.statisticsNow.sessions.map(\.end) == [at(r, 90)])
}

@MainActor @Test func titlesMarkTheSessionAndSongsFollowTheHistory() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(30)
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")                     // a repeat: not a new song
    c.onPlayerTitle("Radio 357 - Najlepszy radiowy adres na świecie!")     // the station's name: not a song
    r.scheduler.advance(30)
    c.stop()
    #expect(saved(r).sessions.map(\.titles) == [true])
    #expect(saved(r).songs == [PlayedSong(station: A.name, title: "Leonard Cohen - Everybody Knows", time: at(r, 30))])
    #expect(c.history.count == 1)
}

@MainActor @Test func sessionWithoutTitlesIsMarkedSo() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(60)
    c.stop()
    #expect(saved(r).sessions.map(\.titles) == [false])
}

@MainActor @Test func goingToSleepEndsTheSessionThere() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(10 * 60)
    c.willSleep()
    r.scheduler.advance(8 * 3600)                                          // a night asleep
    c.resumed()
    r.scheduler.advance(2)
    c.onPlayerStarted()
    r.scheduler.advance(60)
    c.stop()
    #expect(saved(r).sessions.map(\.start) == [at(r, 0), at(r, 10 * 60 + 8 * 3600 + 2)])
    #expect(saved(r).sessions.first?.end == at(r, 10 * 60))
}

@MainActor @Test func quittingSavesTheRunningSession() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(3 * 60)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    c.willQuit()
    #expect(saved(r).sessions.map(\.end) == [at(r, 3 * 60)])
    #expect(saved(r).songs.map(\.title) == ["Queen - A Kind Of Magic"])
}

@MainActor @Test func statisticsAreLoadedAtStart() throws {
    let r = Rig()
    let log = StatisticsLog(sessions: [ListeningSession(station: "Old", url: "http://old/1", start: localDate(2026, 11, 1, 18, 0),
                                                         end: localDate(2026, 11, 1, 19, 0), titles: false)])
    try saveStatistics(r.paths.statisticsFile, log)
    r.controller.start(autostart: true)
    #expect(r.controller.statistics == log)
}

@MainActor @Test func clearStatisticsKeepsTheHistoryAndTheOtherWayRound() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(60)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    r.scheduler.advance(60)
    c.clearHistory()
    #expect(c.statisticsNow.songs.count == 1 && c.statisticsNow.sessions.count == 1)
    var seen: [Change] = []
    c.subscribe { seen.append($0) }
    c.clearStatistics()
    #expect(c.history.isEmpty && saved(r) == StatisticsLog() && seen.contains { $0.contains(.statistics) })
    r.scheduler.advance(60)                                                // still playing: counts on from the clearing
    c.stop()
    #expect(saved(r).sessions.map(\.start) == [at(r, 120)] && saved(r).sessions.map(\.end) == [at(r, 180)])
}

@MainActor @Test func historyClearDoesNotTouchStatistics() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    r.scheduler.advance(60)
    c.stop()
    c.clearHistory()
    #expect(saved(r).songs.count == 1 && saved(r).sessions.count == 1)
}

// MARK: - The Statistics switch (Settings)

@MainActor @Test func switchedOffNothingNewIsRecorded() {
    var prefs = Preferences()
    prefs.collectStatistics = false
    let r = Rig.started(prefs: prefs), c = r.controller
    playing(c)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    r.scheduler.advance(10 * 60)
    c.stop()
    #expect(c.statistics == StatisticsLog() && saved(r) == StatisticsLog())
    #expect(c.history.map(\.title) == ["Queen - A Kind Of Magic"])        // the history goes on
}

@MainActor @Test func switchingOffEndsTheSessionAndKeepsWhatWasCollected() {
    let r = Rig.started(), c = r.controller
    playing(c)
    r.scheduler.advance(60)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    r.scheduler.advance(60)
    var seen: [Change] = []
    c.subscribe { seen.append($0) }
    c.setCollectStatistics(false)
    #expect(loadPreferences(r.paths.preferencesFile).collectStatistics == false)
    #expect(seen.contains { $0.contains(.preferences) })
    #expect(saved(r).sessions.map(\.end) == [at(r, 120)] && saved(r).songs.count == 1)
    c.onPlayerTitle("Editors - Shadow")
    r.scheduler.advance(5 * 60)
    c.stop()
    #expect(saved(r).sessions.map(\.end) == [at(r, 120)] && saved(r).songs.count == 1)
}

@MainActor @Test func switchingOnWhilePlayingStartsCountingThere() {
    var prefs = Preferences()
    prefs.collectStatistics = false
    let r = Rig.started(prefs: prefs), c = r.controller
    playing(c)
    r.scheduler.advance(60)
    c.setCollectStatistics(true)
    r.scheduler.advance(60)
    c.stop()
    #expect(saved(r).sessions.map(\.start) == [at(r, 60)] && saved(r).sessions.map(\.end) == [at(r, 120)])
}

@Test func collectedSinceIsTheFirstSession() {
    #expect(StatisticsLog().since == nil)
    let log = StatisticsLog(sessions: [
        ListeningSession(station: "B", url: "http://b/1", start: localDate(2026, 3, 2, 20, 0), end: localDate(2026, 3, 2, 21, 0), titles: false),
        ListeningSession(station: "A", url: "http://a/1", start: localDate(2025, 3, 2, 19, 0), end: localDate(2025, 3, 2, 20, 0), titles: false),
    ], songs: [PlayedSong(station: "A", title: "Old - Song", time: localDate(2024, 1, 1, 12, 0))])
    #expect(log.since == localDate(2025, 3, 2, 19, 0))                     // sessions, not songs
}

@MainActor @Test func removingAStationKeepsItsStatistics() {
    let r = Rig.started(), c = r.controller
    playing(c, 1)
    r.scheduler.advance(60)
    c.stop()
    c.removeStation(1)
    #expect(saved(r).sessions.map(\.url) == [B.url])
}
