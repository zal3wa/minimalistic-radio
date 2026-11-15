import Foundation
import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_storage.py (the Linux XDG test becomes the Library one).

@Test func standardPathsAreInLibrary() {
    let p = Paths.standard()
    #expect(p.support.path.hasSuffix("Library/Application Support/Minimalistic Radio"))
    #expect(p.cache.path.hasSuffix("Library/Caches/io.github.zal3wa.minimalistic-radio"))
    #expect(p.stationsFile == p.support.appendingPathComponent("stations.json"))
    #expect(p.preferencesFile == p.support.appendingPathComponent("preferences.json"))
    #expect(p.historyFile == p.support.appendingPathComponent("history.json"))
    #expect(p.statisticsFile == p.support.appendingPathComponent("statistics.json"))
    #expect(p.logosFolder == p.cache.appendingPathComponent("logos"))
    #expect(p.coversFolder == p.cache.appendingPathComponent("covers"))
}

@Test func readsWindowsStationFileWithBom() throws {
    let f = tempFolder().appendingPathComponent("stations.json")
    var data = Data([0xEF, 0xBB, 0xBF])
    data.append(Data(#"[{"Name":"RMF FM","Url":"http://rs6.rmf.pl/rmf_fm","Logo":null},{"Name":"","Url":"http://x.pl/a","Logo":null},{"Name":"Bad","Url":"ftp://x","Logo":null}]"#.utf8))
    try data.write(to: f)
    let loaded = loadStations(f)
    #expect(loaded.stations == [Station(name: "RMF FM", url: "http://rs6.rmf.pl/rmf_fm", logo: nil)])
    #expect(loaded.wasCorrupt == false)
}

@Test func savedStationsUseWindowsShape() throws {
    let f = tempFolder().appendingPathComponent("stations.json")
    try saveStations(f, [Station(name: "Radio 357", url: "https://stream.radio357.pl/", logo: "https://x/l.png"),
                         Station(name: "RMF FM", url: "http://rs6.rmf.pl/rmf_fm", logo: nil)])
    let json = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: f)) as? [[String: Any]])
    #expect(json.count == 2)
    #expect(json[0]["Name"] as? String == "Radio 357")
    #expect(json[0]["Url"] as? String == "https://stream.radio357.pl/")
    #expect(json[0]["Logo"] as? String == "https://x/l.png")
    #expect(Set(json[1].keys) == ["Name", "Url", "Logo"])
    #expect(json[1]["Logo"] is NSNull)
}

@Test func corruptStationsMovedAside() throws {
    let folder = tempFolder()
    let f = folder.appendingPathComponent("stations.json")
    try Data("[{".utf8).write(to: f)
    let loaded = loadStations(f)
    #expect(loaded.stations.isEmpty && loaded.wasCorrupt)
    #expect(try String(contentsOf: folder.appendingPathComponent("stations.json.bad"), encoding: .utf8) == "[{")
    #expect(!FileManager.default.fileExists(atPath: f.path))
}

@Test func missingFilesGiveDefaults() {
    let folder = tempFolder()
    let loaded = loadStations(folder.appendingPathComponent("none.json"))
    #expect(loaded.stations.isEmpty && !loaded.wasCorrupt)
    #expect(loadPreferences(folder.appendingPathComponent("none.json")) == Preferences())
    #expect(loadHistory(folder.appendingPathComponent("none.json")).isEmpty)
}

@Test func preferencesAreClampedAndValidated() throws {
    let f = tempFolder().appendingPathComponent("p.json")
    try Data(#"{"Volume": 150, "Language": "ru", "LastPlayed": "http://a/b", "ShowStationPopup": false}"#.utf8).write(to: f)
    var expected = Preferences()
    expected.volume = 100
    expected.lastPlayed = "http://a/b"
    expected.showStationPopup = false
    #expect(loadPreferences(f) == expected)
}

@Test func statisticsAreCollectedByDefault() throws {
    #expect(Preferences().collectStatistics)
    let f = tempFolder().appendingPathComponent("p.json")
    try Data(#"{"Volume": 40, "CollectStatistics": 1}"#.utf8).write(to: f)   // not a JSON boolean: the default
    #expect(loadPreferences(f).collectStatistics)
    try Data(#"{"CollectStatistics": false}"#.utf8).write(to: f)
    #expect(!loadPreferences(f).collectStatistics)
}

@Test func preferencesRoundTripAndCorruptFallback() throws {
    let f = tempFolder().appendingPathComponent("p.json")
    var prefs = Preferences()
    prefs.volume = 55
    prefs.lastPlayed = "http://a/b"
    prefs.language = "pl"
    prefs.checkUpdates = false
    prefs.lastUpdateCheck = localDate(2026, 11, 15, 9, 30, 12)
    prefs.updateByDownload = true
    prefs.collectStatistics = false
    try savePreferences(f, prefs)
    #expect(loadPreferences(f) == prefs)
    try Data("{oops".utf8).write(to: f)
    #expect(loadPreferences(f) == Preferences())
    #expect(FileManager.default.fileExists(atPath: f.path))
}

@Test func historyRoundTripKeeps100() throws {
    let f = tempFolder().appendingPathComponent("h.json")
    let entries = (0..<120).map { HistoryEntry(title: "Song \($0)", station: "S", time: localDate(2026, 11, 14, 19, 52)) }
    try saveHistory(f, entries)
    #expect(loadHistory(f) == Array(entries.prefix(100)))
}

@Test func historyReadsLinuxTimes() throws {
    let f = tempFolder().appendingPathComponent("h.json")
    try Data(#"[{"Title": "A - B", "Station": "S", "Time": "2026-11-14T19:52:00"}, {"Title": 5}]"#.utf8).write(to: f)
    #expect(loadHistory(f) == [HistoryEntry(title: "A - B", station: "S", time: localDate(2026, 11, 14, 19, 52))])
}

@Test func failedSaveKeepsTheOldFile() throws {
    let folder = tempFolder()
    let f = folder.appendingPathComponent("stations.json")
    try saveStations(f, [Station(name: "A", url: "http://a/1")])
    try FileManager.default.setAttributes([.posixPermissions: 0o555], ofItemAtPath: folder.path)
    defer { try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: folder.path) }
    #expect(throws: (any Error).self) { try saveStations(f, []) }
    #expect(loadStations(f).stations == [Station(name: "A", url: "http://a/1")])
}
