import Foundation
import Testing
@testable import RadioCore

// One cleanup for names from every source (docs/superpowers/specs/2026-11-16-security-hardening-design.md, "Names"):
// control and bidirectional formatting characters go, emoji joiners and variation selectors stay, 100 characters.

private let family = "\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}"     // 👨‍👩‍👧: zero-width joiners
private let heart = "\u{2764}\u{FE0F}"                                    // ❤️: a variation selector

@Test func bidiFormattingCharactersAreRemoved() {
    let marks = "\u{061C}\u{200E}\u{200F}\u{202A}\u{202B}\u{202C}\u{202D}\u{202E}\u{2066}\u{2067}\u{2068}\u{2069}"
    #expect(cleanName("Radio\u{202E}MF FM" + marks + "!") == "RadioMF FM!")
    #expect(withoutHiddenCharacters("a\u{2066}b\u{2069}c") == "abc")
}

@Test func controlCharactersAreRemoved() {
    #expect(cleanName("Ra\u{07}dio\r\n\tZłote\u{7F}\u{85}") == "RadioZłote")
}

@Test func emojiJoinersAndVariationSelectorsStay() {
    let name = "\(family) Rodzina \(heart)"
    #expect(cleanName(name) == name)
    #expect(cleanName(name).unicodeScalars.contains("\u{200D}"))
    #expect(cleanName(name).unicodeScalars.contains("\u{FE0F}"))
}

@Test func namesAreTrimmedAndCutTo100() {
    let long = String(repeating: "ab", count: 80)
    #expect(cleanName("  \u{202E} " + long + "\n") == String(long.prefix(100)))
    #expect(cleanName(String(repeating: "x", count: 99) + " y") == String(repeating: "x", count: 99))
    #expect(cleanName(" \u{200E}\t ") == "")
    #expect(cleanName(nil) == "")
}

// MARK: - Every source

@Test func shareLinkNamesLoseBidiCharactersAndKeepEmoji() {
    let link = "minimalistic-radio://add?u=http%3A%2F%2Fa.example&n=" + formEncode("Jazz\u{202E}\u{2066} \(family)")
    #expect(readShareLink(link) == .station(SharedStation(name: "Jazz \(family)", url: "http://a.example", logo: nil)))
}

@Test func directoryNamesAreCleaned() {
    let items: [[String: Any]] = [
        ["name": "  Jazz\u{202E} FM\u{07} ", "url": "http://a.example/1"],
        ["name": "\u{200F}\u{202D}", "url": "http://b.example/1"],                // nothing left: skipped
        ["name": String(repeating: "R", count: 150), "url": "http://c.example/1"],
    ]
    #expect(parseResults(items).map(\.name) == ["Jazz FM", String(repeating: "R", count: 100)])
}

@MainActor @Test func addedAndEditedStationsAreCleaned() {
    let r = Rig.started(), c = r.controller
    #expect(c.addStation(Station(name: "\u{202E}Delta \(heart)", url: "http://d.example/live")) == .added)
    #expect(c.stations.last?.name == "Delta \(heart)" && r.savedNames.last == "Delta \(heart)")
    #expect(c.addStation(Station(name: "\u{202E}\u{2069} ", url: "http://e.example/live")) == .invalid)
    #expect(c.updateStation(0, Station(name: String(repeating: "A", count: 120) + "\u{2066}", url: A.url)) == .added)
    #expect(c.stations[0].name == String(repeating: "A", count: 100))
}

@MainActor @Test func importedNamesAreCleaned() throws {
    let r = Rig.started(stations: []), c = r.controller
    let file = tempFolder().appendingPathComponent("export.json")
    let items: [[String: Any]] = [
        ["Name": "Rock\u{202E}\u{07} Radio", "Url": "http://r.example/1", "Logo": NSNull()],
        ["Name": "\u{2067}\u{2069}", "Url": "http://s.example/1", "Logo": NSNull()],   // nothing left: skipped
        ["Name": String(repeating: "B", count: 130), "Url": "http://t.example/1", "Logo": NSNull()],
    ]
    try JSONSerialization.data(withJSONObject: items).write(to: file)
    #expect(c.importStations(file) == ImportResult(added: 2, error: nil))
    #expect(c.stations.map(\.name) == ["Rock Radio", String(repeating: "B", count: 100)])
}

@Test func stationFileNamesAreCleanedOnLoad() throws {
    let file = tempFolder().appendingPathComponent("stations.json")
    let items: [[String: Any]] = [
        ["Name": "\u{202E}Jazz\u{0D}\u{0A}", "Url": "http://j.example/1", "Logo": NSNull()],
        ["Name": "\u{200E}", "Url": "http://k.example/1", "Logo": NSNull()],          // nothing left: skipped
        ["Name": String(repeating: "C", count: 140) + " \(family)", "Url": "http://l.example/1", "Logo": NSNull()],
    ]
    try JSONSerialization.data(withJSONObject: items).write(to: file)
    #expect(loadStations(file).stations.map(\.name) == ["Jazz", String(repeating: "C", count: 100)])
}

@Test func songTitlesGetTheSameCleanupAndKeep240() {
    #expect(parseTitle("Queen\u{202E} - A Kind\u{07} Of Magic\u{2066}", kind: "generic") == "Queen - A Kind Of Magic")
    #expect(parseTitle("Queen - Magic &#8238;x", kind: "generic") == "Queen - Magic x")             // an entity, too
    #expect(parseTitle("\(family) - \(heart)", kind: "generic") == nil)                           // no letters
    #expect(parseTitle("Abba - \(heart) Song", kind: "generic") == "Abba - \(heart) Song")
    #expect(parseTitle(String(repeating: "\u{202E}A", count: 300), kind: "generic") == String(repeating: "A", count: 240) + "…")
}
