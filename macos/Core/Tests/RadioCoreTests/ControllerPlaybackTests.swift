import CryptoKit
import Foundation
import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_controller.py: playback, reconnecting, titles, covers, volume, sleep timer.

private let itunes: [String: Any] = ["results": [["artistName": "Leonard Cohen", "artworkUrl100": "https://is1.example/a/100x100bb.jpg"]]]
private let bigCover = "https://is1.example/a/600x600bb.jpg"

private func coverFile(_ r: Rig, _ url: String) -> URL {
    let hex = Insecure.SHA1.hash(data: Data(url.utf8)).map { String(format: "%02x", $0) }.joined()
    return r.paths.coversFolder.appendingPathComponent(hex + ".jpg")
}

/// The first station never starts: two retries, then the third network error stops it.
@MainActor private func giveUpOnNetwork(_ r: Rig) {
    let c = r.controller
    c.select(0)
    c.play()
    for delay in [2.0, 3.0] {
        c.onPlayerError(.network, detail: "x")
        r.scheduler.advance(delay)
    }
    c.onPlayerError(.network, detail: "x")
    #expect(c.status == .stopped)
}

private func prefs(lastPlayed: String? = nil, volume: Int = 30) -> Preferences {
    var p = Preferences()
    p.lastPlayed = lastPlayed
    p.volume = volume
    return p
}

// MARK: - Playback and reconnecting

@MainActor @Test func startPlaysLastStationUnlessAutostart() {
    let r = Rig(stations: [A, B], prefs: prefs(lastPlayed: B.url))
    r.controller.start(autostart: false)
    #expect(r.controller.current == 1 && r.player.calls.last == .play(B.url) && r.controller.status == .connecting)
    let r2 = Rig(stations: [A, B], prefs: prefs(lastPlayed: B.url))
    r2.controller.start(autostart: true)
    #expect(r2.controller.current == 1 && !r2.player.calls.contains(.play(B.url)))
}

@MainActor @Test func startedSavesLastPlayedAndStatus() {
    let r = Rig.started(), c = r.controller
    playing(c)
    #expect(c.status == .playing && loadPreferences(r.paths.preferencesFile).lastPlayed == A.url)
}

@MainActor @Test func reconnectBackoffAfterPlaying() {
    let r = Rig.started(), c = r.controller
    playing(c)
    var delays: [Double] = []
    for _ in 0..<10 {
        c.onPlayerError(.network, detail: "lost")
        delays.append(r.scheduler.nextDelay ?? -1)
        r.scheduler.advance(delays.last!)
    }
    #expect(delays == [2, 3, 5, 10, 15, 30, 30, 30, 30, 30])
    c.onPlayerError(.network, detail: "lost")
    #expect(c.status == .stopped && c.message == "lost")
}

@MainActor @Test func neverPlayedGetsTwoRetries() {
    let r = Rig.started()
    giveUpOnNetwork(r)
}

@MainActor @Test func retryCounterResetsAfterAMinuteOfPlaying() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerError(.network, detail: "x")
    #expect(r.scheduler.nextDelay == 2)                                    // t = 0
    r.scheduler.advance(2); c.onPlayerStarted(); r.scheduler.advance(61)   // played 61 s
    c.onPlayerError(.network, detail: "x")
    #expect(r.scheduler.nextDelay == 2)
    r.scheduler.advance(2); c.onPlayerStarted(); r.scheduler.advance(59)   // only 59 s: no reset
    c.onPlayerError(.network, detail: "x")
    #expect(r.scheduler.nextDelay == 3)
}

@MainActor @Test func retryingMessage() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerError(.network, detail: "x")
    #expect(c.status == .retrying && c.message == "Connection lost. Retrying in 2 s…")
}

@MainActor @Test func refusedAndUnsupportedStopAtOnce() {
    let r = Rig.started(), c = r.controller
    for kind in [ErrorKind.refused, .unsupported] {
        c.select(0)
        c.play()
        c.onPlayerError(kind, detail: "nope")
        #expect(c.status == .stopped && r.scheduler.pending == 0)
    }
}

@MainActor @Test func eosRetriesThenSaysBroadcastEnded() {
    let r = Rig.started(), c = r.controller
    playing(c)
    for delay in [2.0, 3, 5, 10, 15, 30, 30, 30, 30, 30] {
        c.onPlayerEOS()
        #expect(c.status == .retrying && r.scheduler.nextDelay == delay)
        r.scheduler.advance(delay)
        #expect(c.status == .connecting && r.player.calls.last == .play(A.url))
    }
    c.onPlayerEOS()
    #expect(c.status == .stopped && c.message == "The broadcast has ended" && r.scheduler.pending == 0)
    // The last failure decides: an error after an end of stream is reported as the error.
    c.select(1)
    c.play()
    c.onPlayerEOS(); r.scheduler.advance(2); c.onPlayerEOS(); r.scheduler.advance(3)
    c.onPlayerError(.network, detail: "timeout")
    #expect(c.status == .stopped && c.message == "timeout")
}

@MainActor @Test func networkReturnRestartsAfterGivingUpOnNetwork() {
    let r = Rig.started(), c = r.controller
    giveUpOnNetwork(r)
    r.scheduler.advance(9 * 60)
    c.networkAvailable()
    #expect(c.status == .connecting && c.current == 0 && r.player.calls.last == .play(A.url))
    giveUpOnNetwork(r)
    r.scheduler.advance(10 * 60 + 1)
    let calls = r.player.calls
    c.networkAvailable()
    #expect(c.status == .stopped && r.player.calls == calls)
}

@MainActor @Test func networkReturnDoesNotRestartAfterUserStop() {
    let r = Rig.started(), c = r.controller
    func expectNoRestart(_ comment: Comment) {
        let calls = r.player.calls
        c.networkAvailable()
        #expect(c.status == .stopped && r.player.calls == calls, comment)
    }
    playing(c); c.stop(); expectNoRestart("stopped by the user")
    giveUpOnNetwork(r); c.stop(); expectNoRestart("gave up, then Stop")
    c.play(); c.onPlayerError(.refused, detail: "403 Forbidden"); expectNoRestart("refused")
    playing(c); c.setSleepTimer(minutes: 15); r.scheduler.advance(15 * 60)
    #expect(c.message == "Stopped by the sleep timer")
    expectNoRestart("sleep timer")
    playing(c)
    for delay in [2.0, 3, 5, 10, 15, 30, 30, 30, 30, 30] { c.onPlayerEOS(); r.scheduler.advance(delay) }
    c.onPlayerEOS()
    #expect(c.message == "The broadcast has ended")
    expectNoRestart("broadcast ended")
    giveUpOnNetwork(r); c.select(1)                                        // another station chosen
    let calls = r.player.calls
    c.networkAvailable()
    #expect(c.status == .ready && r.player.calls == calls)
}

@MainActor @Test func networkReturnSkipsBackoffWhileRetrying() {
    let r = Rig.started(), c = r.controller
    playing(c)
    for delay in [2.0, 3, 5, 10, 15] { c.onPlayerError(.network, detail: "x"); r.scheduler.advance(delay) }
    c.onPlayerError(.network, detail: "x")
    #expect(c.status == .retrying && r.scheduler.nextDelay == 30)
    c.networkAvailable()
    #expect(c.status == .connecting && r.player.calls.last == .play(A.url) && r.scheduler.pending == 0)
}

@MainActor @Test func resumedRestartsActiveSession() {
    let r = Rig.started(), c = r.controller
    playing(c); r.player.calls.removeAll()
    c.resumed()
    #expect(c.status == .connecting && r.player.calls.last == .play(A.url))
    c.stop(); r.player.calls.removeAll()
    c.resumed()
    #expect(c.status == .stopped && r.player.calls.isEmpty)
    giveUpOnNetwork(r); c.resumed()                                        // same rule as the network
    #expect(c.status == .connecting && r.player.calls.last == .play(A.url))
}

@MainActor @Test func playKeepsAStationThatIsAlreadyOn() {
    let r = Rig.started(), c = r.controller
    playing(c); r.player.calls.removeAll()
    c.play()
    #expect(c.status == .playing && r.player.calls.isEmpty)
}

@MainActor @Test func togglePlaysTheFirstStationWhenNoneIsChosen() {
    let r = Rig.started(), c = r.controller
    c.toggle()
    #expect(c.current == 0 && c.status == .connecting && r.player.calls.last == .play(A.url))
    c.toggle()
    #expect(c.status == .stopped && r.player.calls.last == .stop)
}

@MainActor @Test func playWithoutStationsReturnsFalse() {
    let r = Rig.started(stations: []), c = r.controller
    r.player.calls.removeAll()
    #expect(c.play() == false)
    #expect(r.player.calls.isEmpty && c.status == .ready)
}

@MainActor @Test func quickSwitchesConnectOnceToTheLastStation() {
    let r = Rig.started(), c = r.controller
    playing(c); r.player.calls.removeAll()
    for _ in 0..<5 { c.nextStation(); r.scheduler.advance(0.05) }          // five presses within 300 ms
    #expect(c.current == 2 && c.status == .connecting && r.player.calls.isEmpty)
    r.scheduler.advance(0.3)
    #expect(r.player.calls == [.play(C.url)])
}

// MARK: - Sleep timer

@MainActor @Test func sleepTimerFadesLast30SecondsThenStops() {
    let r = Rig.started(), c = r.controller
    playing(c); c.setVolume(60); c.setSleepTimer(minutes: 15)
    r.scheduler.advance(15 * 60 - 15)
    #expect(c.effectiveVolume == 30)
    r.scheduler.advance(15)
    #expect(c.status == .stopped && c.message == "Stopped by the sleep timer" && c.sleepAt == nil)
}

@MainActor @Test func sleepTimerOff() {
    let r = Rig.started(), c = r.controller
    c.setSleepTimer(minutes: 30)
    c.setSleepTimer(minutes: nil)
    #expect(c.sleepAt == nil && r.scheduler.pending == 0)
}

@MainActor @Test func sleepTimerEndCancelsANetworkComeback() {
    let r = Rig.started(), c = r.controller
    playing(c); c.setSleepTimer(minutes: 15)
    r.scheduler.advance(10 * 60)                                           // the Wi-Fi drops at minute 10
    for delay in [2.0, 3, 5, 10, 15, 30, 30, 30, 30, 30] { c.onPlayerError(.network, detail: "lost"); r.scheduler.advance(delay) }
    c.onPlayerError(.network, detail: "lost")                              // gives up around minute 13
    #expect(c.status == .stopped && c.gaveUpOnNetworkAt != nil)
    r.scheduler.advance(5 * 60)                                            // the timer ends at minute 15
    #expect(c.sleepAt == nil && c.gaveUpOnNetworkAt == nil)
    let calls = r.player.calls
    c.networkAvailable(); c.resumed()                                      // the network is back at minute 18
    #expect(c.status == .stopped && r.player.calls == calls)
}

@MainActor @Test func sleepTimerRestoresVolumeWhenTurnedOff() {
    let r = Rig.started(), c = r.controller
    playing(c); c.setVolume(60); c.setSleepTimer(minutes: 15)
    #expect(c.sleepMinutes == 15 && c.sleepAt == r.scheduler.start.addingTimeInterval(15 * 60))
    r.scheduler.advance(15 * 60 - 6)
    #expect(r.player.calls.last == .setVolume(12))
    c.setSleepTimer(minutes: nil)
    #expect(c.effectiveVolume == 60 && r.player.calls.last == .setVolume(60) && c.sleepMinutes == nil)
}

// MARK: - Titles, covers

@MainActor @Test func titleGoesToHistoryOnceAndLooksUpCover() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")
    #expect(c.history.map(\.title) == ["Leonard Cohen - Everybody Knows"])
    #expect(r.net.urls.last?.hasPrefix("https://itunes.apple.com/search?") == true)
}

@MainActor @Test func radio357IgnoresIcyAndPollsEvery10s() {
    let r = Rig.started(stations: [Station(name: "Radio 357", url: "https://stream.radio357.pl/")]), c = r.controller
    let feed = radio357URL.absoluteString
    r.net.responses[feed] = ["s": "Kult - Arahja"]
    func polls() -> Int { r.net.urls.filter { $0 == feed }.count }
    playing(c)
    #expect(polls() == 1 && c.track == "Kult - Arahja")                     // t = 0
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")
    #expect(c.track == "Kult - Arahja")                                    // ICY titles are ignored
    r.scheduler.advance(10)
    #expect(polls() == 2)                                                  // t = 10
    r.net.responses[feed] = .some(nil)                                     // the lookup fails
    r.scheduler.advance(10)
    #expect(polls() == 3 && c.track == nil)                                // t = 20
    c.stop(); r.scheduler.advance(60)
    #expect(polls() == 3)
}

@MainActor @Test func itunesCoverIsDownloadedThenShown() {
    let r = Rig.started(), c = r.controller
    playing(c)
    var seen: [Change] = []
    c.subscribe { seen.append($0) }
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")
    r.net.reply(itunes)
    #expect(r.net.downloads.map { [$0.url.absoluteString, $0.path.path] } == [[bigCover, coverFile(r, bigCover).path]])
    #expect(c.coverPath == nil)
    r.net.finishDownload()
    #expect(c.coverPath == coverFile(r, bigCover) && seen.last?.contains(.cover) == true)
}

@MainActor @Test func coverLookupsAreCached() {
    let r = Rig.started(), c = r.controller
    playing(c)
    // Titles 5 seconds apart: closer ones wait (ControllerTitlesTests).
    c.onPlayerTitle("Leonard Cohen - Everybody Knows"); r.net.reply(itunes); r.net.finishDownload()
    r.scheduler.advance(5)
    c.onPlayerTitle("Dżingiel")                                            // no artist: no lookup, no cover
    #expect(c.coverPath == nil && r.net.urls.count == 1)
    r.scheduler.advance(5)
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")                     // known song, picture already saved
    #expect(r.net.urls.count == 1 && r.net.downloads.isEmpty && c.coverPath == coverFile(r, bigCover))
    r.scheduler.advance(5)
    c.onPlayerTitle("Queen - A Kind Of Magic"); r.net.reply(nil)          // failed: asked again next time
    r.scheduler.advance(5)
    c.onPlayerTitle("Editors - Shadow"); r.net.reply(["results": [Any]()]) // no cover: remembered
    r.scheduler.advance(5)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    r.scheduler.advance(5)
    c.onPlayerTitle("Editors - Shadow")
    #expect(r.net.urls.count == 4 && r.net.urls.last?.hasSuffix("Queen%20A%20Kind%20Of%20Magic") == true)
}

@MainActor @Test func lateCoverForAnEarlierSongIsNotShown() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")
    r.scheduler.advance(5)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    r.net.reply(itunes)
    #expect(r.net.downloads.isEmpty && c.coverPath == nil)
}

@MainActor @Test func coversComeOnlyFromWebAddresses() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Leonard Cohen - Everybody Knows")
    r.net.reply(["results": [["artistName": "Leonard Cohen", "artworkUrl100": "file:///etc/100x100bb.jpg"]]])
    #expect(r.net.downloads.isEmpty && c.coverPath == nil)
}

@MainActor @Test func streamArtworkIsUsedOnlyWithATitle() {
    let r = Rig.started(stations: [Station(name: "KIIS", url: "https://stream.revma.ihrhls.com/zc185")]), c = r.controller
    playing(c)
    c.onPlayerTitle(#"Promo - text="Reklama" song_spot="A" amgArtworkURL="https://img.example/ad.jpg""#)
    #expect(c.track == nil && r.net.downloads.isEmpty)
    let art = "https://img.example/cover.jpg"
    c.onPlayerTitle(#"Sienna Spiro - text="Great Expectation" song_spot="M" amgArtworkURL=""# + art + "\"")
    #expect(c.track == "Sienna Spiro – Great Expectation" && r.net.urls.isEmpty)
    #expect(r.net.downloads.map { [$0.url.absoluteString, $0.path.path] } == [[art, coverFile(r, art).path]])
    r.net.finishDownload()
    #expect(c.coverPath == coverFile(r, art))
}

// MARK: - Volume

@MainActor @Test func volumeClampedSavedAndSent() {
    let r = Rig.started(), c = r.controller
    c.setVolume(130)
    #expect(c.volume == 100 && r.player.calls.last == .setVolume(100))
    #expect(loadPreferences(r.paths.preferencesFile).volume == 100)
}

@MainActor @Test func unmuteGoesBackToBeforeAQuickSlideToZero() {
    let r = Rig.started(), c = r.controller
    c.setVolume(60); r.scheduler.advance(5)
    for level in [40, 1, 0] { c.setVolume(level); r.scheduler.advance(0.1) }   // less than a second apart, like a drag
    c.toggleMute()
    #expect(c.volume == 60)
}

// MARK: - Start

@MainActor @Test func startKeepsThe200NewestCovers() throws {
    let r = Rig(), c = r.controller
    let covers = r.paths.coversFolder
    try FileManager.default.createDirectory(at: covers, withIntermediateDirectories: true)
    for n in 0..<205 {
        let file = covers.appendingPathComponent(String(format: "%03d.jpg", n))
        try Data("cover".utf8).write(to: file)
        try FileManager.default.setAttributes([.modificationDate: Date(timeIntervalSince1970: 1_700_000_000 + Double(n))],
                                              ofItemAtPath: file.path)
    }
    c.start(autostart: true)
    let left = try FileManager.default.contentsOfDirectory(atPath: covers.path).sorted()
    #expect(left == (5..<205).map { String(format: "%03d.jpg", $0) })
}

@MainActor @Test func startKeepsThe200NewestLogos() throws {
    let r = Rig(), c = r.controller
    let logos = r.paths.logosFolder
    try FileManager.default.createDirectory(at: logos, withIntermediateDirectories: true)
    for n in 0..<230 {
        let file = logos.appendingPathComponent(String(format: "%03d", n))
        try Data("logo".utf8).write(to: file)
        try FileManager.default.setAttributes([.modificationDate: Date(timeIntervalSince1970: 1_700_000_000 + Double(n))],
                                              ofItemAtPath: file.path)
    }
    c.start(autostart: true)
    let left = try FileManager.default.contentsOfDirectory(atPath: logos.path).sorted()
    #expect(left == (30..<230).map { String(format: "%03d", $0) })
}
