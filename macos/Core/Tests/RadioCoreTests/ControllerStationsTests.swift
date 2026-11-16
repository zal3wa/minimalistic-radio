import Foundation
import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_controller.py: the station list, preferences and history.

private let notAList = "This isn't a Minimalistic Radio station list."

@MainActor @Test func selectSwitchesOnlyWhilePlaying() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.select(1)
    #expect(c.current == 1 && c.status == .connecting && r.player.calls.last == .play(B.url))
    c.stop()
    r.player.calls.removeAll()
    c.select(2)
    #expect(c.current == 2 && c.status == .ready && r.player.calls.isEmpty)
}

@MainActor @Test func nextPreviousWrapAndFlagSwitch() {
    let r = Rig.started(), c = r.controller
    c.select(0)
    var seen: [Change] = []
    _ = c.subscribe { seen.append($0) }
    c.previousStation()
    #expect(c.current == c.stations.count - 1 && seen.contains { $0.contains(.switched) })
    c.nextStation()
    #expect(c.current == 0)
}

@MainActor @Test func addStationRejectsInvalidAndDuplicates() {
    let r = Rig.started(), c = r.controller
    #expect(c.addStation(Station(name: "", url: "http://x/a")) == .invalid)
    #expect(c.addStation(Station(name: "Copy", url: A.url.replacingOccurrences(of: "http:", with: "https:") + "/")) == .duplicate)
    #expect(c.addStation(Station(name: " New ", url: "http://new/s")) == .added)
    #expect(c.stations.last?.name == "New")
    #expect(c.addStation(Station(name: "Logo", url: "http://logo/s", logo: "javascript:alert(1)")) == .invalid)
    #expect(r.savedNames == ["Alpha", "Beta", "Gamma", "New"])
}

@MainActor @Test func updateStationFollowsThePlayingStation() {
    let r = Rig.started(), c = r.controller
    playing(c, 1)
    #expect(c.updateStation(1, Station(name: "Beta FM", url: B.url, logo: B.logo)) == .added)   // renamed only
    #expect(c.stationName == "Beta FM" && c.status == .playing)
    #expect(c.updateStation(1, Station(name: "Beta FM", url: A.url)) == .duplicate)
    #expect(c.updateStation(1, Station(name: "Beta FM", url: "not an address")) == .invalid)
    #expect(c.updateStation(9, Station(name: "Beta FM", url: "http://b.example/hd")) == .invalid)
    #expect(c.updateStation(1, Station(name: " Beta HD ", url: "http://b.example/hd")) == .added)   // new address
    #expect(r.player.calls.last == .play("http://b.example/hd") && c.status == .connecting)
    #expect(loadStations(r.paths.stationsFile).stations[1] == Station(name: "Beta HD", url: "http://b.example/hd"))
    #expect(loadPreferences(r.paths.preferencesFile).lastPlayed == "http://b.example/hd")
}

@MainActor @Test func moveAndRemoveKeepCurrentStation() {
    let r = Rig.started(), c = r.controller
    func names() -> [String] { c.stations.map(\.name) }
    playing(c, 1)                                                         // Beta
    c.moveStation(from: 1, to: 0)
    #expect(names() == ["Beta", "Alpha", "Gamma"] && c.current == 0)
    #expect(r.savedNames == ["Beta", "Alpha", "Gamma"])
    c.moveStation(from: 0, to: 0)                                         // nowhere, or past either end: nothing
    c.moveStation(from: 0, to: 1)
    c.moveStation(from: 5, to: 0)
    c.moveStation(from: 0, to: 4)
    #expect(names() == ["Beta", "Alpha", "Gamma"])
    c.moveStation(from: 0, to: 3)                                         // the playing station to the end
    #expect(names() == ["Alpha", "Gamma", "Beta"] && c.current == 2 && c.status == .playing)
    c.removeStation(0)
    #expect(names() == ["Gamma", "Beta"] && c.current == 1 && c.status == .playing)
    c.removeStation(1)                                                    // the playing station
    #expect(names() == ["Gamma"] && c.current == -1 && c.status == .stopped)
    #expect(r.player.calls.last == .stop && r.savedNames == ["Gamma"])
    #expect(loadPreferences(r.paths.preferencesFile).lastPlayed == nil)
}

@MainActor @Test func importMergesLikeWindows() throws {
    let r = Rig.started(), c = r.controller
    let f = tempFolder().appendingPathComponent("list.json")
    let list: [Any] = [
        ["Name": "Alpha again", "Url": A.url.replacingOccurrences(of: "http:", with: "https:"), "Logo": NSNull()],   // known stream
        ["Name": " Delta ", "Url": "http://d.example/live", "Logo": "ftp://d.example/logo.png"],
        ["Name": "Delta copy", "Url": "http://D.example/live/", "Logo": NSNull()],                         // same stream as Delta
        ["Name": "Echo", "Url": "https://e.example/stream", "Logo": "https://e.example/logo.png"],
        ["Name": "  ", "Url": "http://f.example/live", "Logo": NSNull()],
        ["Name": "Local", "Url": "file:///etc/passwd", "Logo": NSNull()],
        "junk",
    ]
    var data = Data([0xEF, 0xBB, 0xBF])
    data.append(try JSONSerialization.data(withJSONObject: list))
    try data.write(to: f)
    #expect(c.importStations(f) == ImportResult(added: 2, error: nil))
    #expect(Array(c.stations[3...]) == [Station(name: "Delta", url: "http://d.example/live"),
                                         Station(name: "Echo", url: "https://e.example/stream", logo: "https://e.example/logo.png")])
    #expect(loadStations(r.paths.stationsFile).stations == c.stations)
    #expect(c.importStations(f) == ImportResult(added: 0, error: nil) && c.stations.count == 5)   // all already there
    for content in [#"{"Name": "Alpha"}"#, "[{", ""] {
        try Data(content.utf8).write(to: f)
        #expect(c.importStations(f) == ImportResult(added: 0, error: notAList))
    }
    #expect(FileManager.default.fileExists(atPath: f.path))                                     // never moved aside
    #expect(c.importStations(f.deletingLastPathComponent().appendingPathComponent("missing.json")) == ImportResult(added: 0, error: notAList))
    #expect(c.stations.count == 5)
}

@MainActor @Test func exportWritesWindowsListAndReportsFailure() throws {
    let r = Rig.started(), c = r.controller
    let folder = tempFolder()
    let out = folder.appendingPathComponent("export.json")
    #expect(c.exportStations(out))
    #expect(loadStations(out).stations == [A, B, C])
    let directory = folder.appendingPathComponent("folder.json")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    #expect(!c.exportStations(directory))
    #expect(c.message == nil && c.notice == nil)
}

@MainActor @Test func saveFailuresKeepTheControllerWorking() {
    let r = Rig.started(), c = r.controller
    c.writeStations = { _, _ in throw DiskFull() }
    c.writePreferences = { _, _ in throw DiskFull() }
    c.writeHistory = { _, _ in throw DiskFull() }
    var seen: [Change] = []
    _ = c.subscribe { seen.append($0) }
    #expect(c.addStation(Station(name: "Delta", url: "http://d.example/live")) == .added)
    #expect(c.stations.last?.name == "Delta" && c.notice == "Couldn't save the station list.")
    #expect(seen.contains { $0.contains(.message) })
    playing(c)
    c.setVolume(70)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    c.setLanguage("en")
    #expect(c.volume == 70 && c.history.first?.title == "Queen - A Kind Of Magic" && c.prefs.language == "en")
    #expect(c.status == .playing && c.message == nil)
    #expect(c.updateStation(0, Station(name: "Alpha 2", url: "http://a.example/2")) == .added)   // restarts it
    #expect(c.status == .connecting && c.notice == "Couldn't save the station list.")
    #expect(c.message == nil)   // a notice is never the status line
}

@MainActor @Test func unknownLanguageIgnored() {
    let c = Rig.started().controller
    c.setLanguage("ru")
    #expect(c.prefs.language == "auto")
}

@MainActor @Test func languageAndStationPopupSaved() {
    let r = Rig.started(), c = r.controller
    var seen: [Change] = []
    _ = c.subscribe { seen.append($0) }
    c.setLanguage("pl")
    c.setShowStationPopup(false)
    let saved = loadPreferences(r.paths.preferencesFile)
    #expect(saved.language == "pl" && saved.showStationPopup == false)
    #expect(!seen.isEmpty && seen.allSatisfy { $0.contains(.preferences) })
}

@MainActor @Test func updatePreferencesSaved() {
    let r = Rig.started(), c = r.controller
    let when = localDate(2026, 11, 15, 9, 0)
    c.setCheckUpdates(false)
    c.setLastUpdateCheck(when)
    c.setUpdateByDownload(true)
    let saved = loadPreferences(r.paths.preferencesFile)
    #expect(saved.checkUpdates == false && saved.lastUpdateCheck == when && saved.updateByDownload)
}

@MainActor @Test func startLoadsFilesAndReportsACorruptStationList() throws {
    var prefs = Preferences()
    prefs.volume = 55
    let r = Rig(prefs: prefs), c = r.controller
    try Data("[{".utf8).write(to: r.paths.stationsFile)
    c.start(autostart: false)
    #expect(c.corruptStations && c.stations.isEmpty && c.current == -1 && c.status == .ready)
    #expect(c.volume == 55 && r.player.calls == [.setVolume(55)])
}

@MainActor @Test func historySkipsRepeatsKeeps100AndClears() {
    let r = Rig.started(), c = r.controller
    playing(c)
    c.onPlayerTitle("Queen - A Kind Of Magic")
    c.onPlayerTitle("***")
    c.onPlayerTitle("Queen - A Kind Of Magic")
    #expect(c.history.map(\.title) == ["Queen - A Kind Of Magic"] && c.history.first?.station == "Alpha")
    #expect(c.history.first?.time == r.scheduler.now())
    for n in 0..<105 {                                                     // 5 seconds apart, as titles are applied
        r.scheduler.advance(5)
        c.onPlayerTitle("Artist - Song \(n)")
    }
    #expect(c.history.count == 100 && c.history.first?.title == "Artist - Song 104")
    #expect(loadHistory(r.paths.historyFile).map(\.title) == c.history.map(\.title))
    c.clearHistory()
    #expect(c.history.isEmpty && loadHistory(r.paths.historyFile).isEmpty)
}
