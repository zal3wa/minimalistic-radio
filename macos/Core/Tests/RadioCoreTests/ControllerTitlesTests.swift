import Foundation
import Testing
@testable import RadioCore

// A flood of song titles can't slow the radio down: a stream's title changes are applied at most once every
// 5 seconds, the first one at once and the newest one when the 5 seconds have passed. History, statistics and
// covers see only the titles applied.

@MainActor private func tracksSeen(_ c: RadioController) -> () -> [String?] {
    var seen: [String?] = []
    c.subscribe { if $0.contains(.track) { seen.append(c.track) } }
    return { seen }
}

@MainActor @Test func firstTitleAtOnceThenTheNewestAfter5Seconds() {
    let r = Rig.started(), c = r.controller
    playing(c)
    let seen = tracksSeen(c)
    c.onPlayerTitle("Abba - One")
    #expect(c.track == "Abba - One")                                       // t = 0: at once
    r.scheduler.advance(1); c.onPlayerTitle("Abba - Two")
    r.scheduler.advance(1); c.onPlayerTitle("Abba - Three")
    r.scheduler.advance(2.9)
    #expect(c.track == "Abba - One")                                       // t = 4.9
    r.scheduler.advance(0.1)
    #expect(c.track == "Abba - Three")                                     // t = 5: the newest
    #expect(seen() == ["Abba - One", "Abba - Three"])
    #expect(c.history.map(\.title) == ["Abba - Three", "Abba - One"])
}

@MainActor @Test func titleAfterAQuietSpellIsAppliedAtOnce() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Abba - One")
    r.scheduler.advance(5)
    c.onPlayerTitle("Abba - Two")
    #expect(c.track == "Abba - Two")
    r.scheduler.advance(30)
    c.onPlayerTitle("Abba - Three")
    #expect(c.track == "Abba - Three")
}

@MainActor @Test func repeatsOfTheShownTitleDoNotDelayTheNextOne() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Abba - One")
    for _ in 0..<10 { r.scheduler.advance(1); c.onPlayerTitle("Abba - One") }   // some streams repeat it every second
    c.onPlayerTitle("Abba - Two")
    #expect(c.track == "Abba - Two")
}

@MainActor @Test func aFloodOfTitlesReachesHistoryStatisticsAndCoversOnlyOnceEvery5Seconds() {
    let r = Rig.started(), c = r.controller
    playing(c)
    for n in 0..<1000 { c.onPlayerTitle("Artist \(n) - Song \(n)") }     // 1000 titles at once
    #expect(c.track == "Artist 0 - Song 0")
    r.scheduler.advance(5)
    #expect(c.track == "Artist 999 - Song 999")
    for n in 1000..<2000 { c.onPlayerTitle("Artist \(n) - Song \(n)") }  // and 1000 more
    #expect(c.track == "Artist 999 - Song 999")
    r.scheduler.advance(5)
    #expect(c.track == "Artist 1999 - Song 1999")
    #expect(c.history.map(\.title) == ["Artist 1999 - Song 1999", "Artist 999 - Song 999", "Artist 0 - Song 0"])
    #expect(c.statistics.songs.count == 3)
    #expect(r.net.urls.filter { $0.hasPrefix("https://itunes.apple.com/") }.count == 3)
}

@MainActor @Test func aWaitingTitleIsDroppedWhenTheStationStopsOrChanges() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Abba - One")
    c.onPlayerTitle("Abba - Two")
    c.stop()
    r.scheduler.advance(10)
    #expect(c.track == nil && c.history.map(\.title) == ["Abba - One"])

    playing(c, 1)
    c.onPlayerTitle("Queen - Magic")                                       // a new station: at once
    #expect(c.track == "Queen - Magic")
    c.onPlayerTitle("Queen - Flash")
    c.select(2)                                                            // another station while playing
    r.scheduler.advance(10)
    #expect(c.track == nil && !c.history.map(\.title).contains("Queen - Flash"))
    c.onPlayerStarted()
    c.onPlayerTitle("Editors - Shadow")
    #expect(c.track == "Editors - Shadow")
}

@MainActor @Test func aWaitingTitleIsDroppedWhenTheConnectionIsLost() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Abba - One")
    c.onPlayerTitle("Abba - Two")
    c.onPlayerError(.network, detail: "lost")                              // retrying in 2 s
    r.scheduler.advance(2)
    c.onPlayerStarted()
    r.scheduler.advance(10)
    #expect(c.track == nil && c.history.map(\.title) == ["Abba - One"])
    c.onPlayerTitle("Abba - Three")                                        // reconnected: at once
    #expect(c.track == "Abba - Three")
}
