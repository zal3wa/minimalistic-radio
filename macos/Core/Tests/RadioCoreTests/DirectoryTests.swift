import Foundation
import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_directory.py (without the Linux locale parser and the ban-list copy check),
// plus the Mac's playable filter.

private struct Down: Error {}

private let repoBanList = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().deletingLastPathComponent()
    .appendingPathComponent("data/banned-stations.json")
private let bans = BanList.load(repoBanList)

private func entry(_ name: String, _ url: String? = nil, id: String = "") -> DirectoryStation {
    DirectoryStation(name: name, country: "", url: url ?? "http://x/\(name)", logo: nil, codec: "MP3", bitrate: 128,
                     tags: "", id: id)
}

private func banned(_ name: String, _ code: String, _ url: String, uuid: String = "") -> DirectoryStation {
    DirectoryStation(name: name, country: "", url: url, logo: nil, codec: "MP3", bitrate: 128, tags: "", id: uuid,
                     working: true, countryCode: code)
}

@Test func searchURLEncodesTheQuery() {
    #expect(searchURL(server: "de1.api.radio-browser.info", query: "rock & roll").absoluteString
            == "https://de1.api.radio-browser.info/json/stations/search?hidebroken=true&limit=40&order=clickcount&reverse=true&name=rock%20%26%20roll")
}

@Test func parsePrefersResolvedURLAndDedupes() {
    let items: [[String: Any]] = [
        ["name": "Jazz", "url": "http://a/pls", "url_resolved": "http://a/stream", "favicon": "https://a/i.png", "codec": "MP3",
         "bitrate": 192, "tags": "jazz,smooth jazz,lounge", "country": "Germany"],
        ["name": "Jazz copy", "url": "http://a/stream", "url_resolved": "", "codec": "MP3"],
        ["name": "", "url": "http://b/s"], ["name": "NoUrl", "url": "nope"],
    ]
    let found = parseResults(items)
    #expect(found.map(\.name) == ["Jazz"])
    #expect(found.first?.url == "http://a/stream")
}

@Test func subtitleMatchesWindowsFormat() {
    let e = DirectoryStation(name: "X", country: "Germany ", url: "http://a/s", logo: nil, codec: "mp3", bitrate: 192,
                             tags: "jazz, smooth jazz ,lounge")
    #expect(subtitle(e) == "Germany · MP3 192 kbps · jazz, smooth jazz")
    #expect(subtitle(DirectoryStation(name: "X", country: "", url: "http://a/s", logo: nil, codec: "UNKNOWN", bitrate: 0, tags: "")) == "")
}

@Test func toStationDropsBadLogo() {
    let e = DirectoryStation(name: " Jazz ", country: "", url: "http://a/s", logo: "data:x", codec: "MP3", bitrate: 0, tags: "")
    #expect(toStation(e) == Station(name: "Jazz", url: "http://a/s", logo: nil))
}

@Test func searchFallsBackToSecondServer() async throws {
    var calls: [String] = []
    let found = try await search("a", bans: .none) { url in
        calls.append(url.absoluteString)
        if url.host?.hasPrefix("de1") == true { throw Down() }
        return [["name": "A", "url": "http://a/s"]]
    }
    #expect(found.map(\.name) == ["A"])
    #expect(calls.count == 2)
}

@Test func searchAllServersDown() async {
    await #expect(throws: DirectoryError.unavailable) {
        _ = try await search("a", bans: .none) { _ in throw Down() }
    }
}

@Test func searchHidesWhatTheMacCantPlay() async throws {
    let found = try await search("a", bans: .none) { _ in
        [["name": "Ogg", "url": "http://a/o", "codec": "OGG"],
         ["name": "Hls", "url": "http://a/h", "codec": "AAC", "hls": 1],
         ["name": "Mp3", "url": "http://a/m", "codec": "MP3"]]
    }
    #expect(found.map(\.name) == ["Hls", "Mp3"])
}

@Test func hlsIsPlayableOnTheMac() {
    #expect(playable(codec: "AAC", hls: true))
    #expect(playable(codec: "AAC+", hls: false) && playable(codec: "unknown", hls: false) && playable(codec: nil, hls: false))
    #expect(!playable(codec: "OGG", hls: false))
    #expect(!playable(codec: "FLAC", hls: false))
}

@Test(arguments: ["-- # TOP 100 CHARTS ---", "0R - LO-FI || LoFi, Chill, Study, Hip Hop, Relax",
                  "*Chill", "Lofi || Chill", "Hits #1", "Top ***", "a, b, c, d, e"])
func spam(name: String) {
    #expect(looksLikeSpam(name))
}

@Test(arguments: ["RMF FM", "102.7 KIIS FM Los Angeles", "Radio ZET Chilli", "Rock, Pop, Jazz, Blues"])
func notSpam(name: String) {
    #expect(!looksLikeSpam(name))
}

@Test func nameKeyIgnoresTheWordRadio() {
    #expect(nameKey("Radio RMF FM") == "rmffm")
    #expect(nameKey("RMF FM") == "rmffm")
    #expect(nameKey("Radio") == "")
}

@Test func cleanPopularRules() {
    func names(_ items: [DirectoryStation]) -> [String] { items.map(\.name) }
    #expect(names(cleanPopular(["RMF FM", "Radio RMF FM", "Radio ZET", "Radio ZET Chilli"].map { entry($0) }, recommended: []))
            == ["RMF FM", "Radio ZET", "Radio ZET Chilli"])
    #expect(names(cleanPopular([entry("Radio", "http://a"), entry("Radio", "http://b")], recommended: [])) == ["Radio", "Radio"])
    #expect(names(cleanPopular([entry("A", "http://s"), entry("B", "http://s/")], recommended: [])) == ["A"])
    #expect(names(cleanPopular([entry("KEXP"), entry("Other", "http://r"), entry("Third")],
                               recommended: [entry("Radio KEXP"), entry("Z", "http://r")])) == ["Third"])
    #expect(cleanPopular((0..<30).map { entry("S\($0)") }, recommended: []).count == 15)
}

@Test(arguments: [("pl", "US", "PL"), ("pl", nil, "PL"), ("es", "MX", "MX"), ("es", "US", "ES"), ("en", "US", "US"),
                  ("en", nil, nil), ("de", "AT", "AT"), ("pt", "BR", "BR")] as [(String, String?, String?)])
func countryForLanguage(language: String, system: String?, expected: String?) {
    #expect(countryFor(language: language, systemCountry: system) == expected)
}

@Test func languageOfTheFirstPreferredLanguage() {
    #expect(languageOf(["pl-PL", "en"]) == "pl")
    #expect(languageOf(["pt_BR.UTF-8"]) == "pt")
    #expect(languageOf([]) == "en")
}

@Test func suggestionURLs() {
    #expect(recommendedURL(server: "s").absoluteString.hasPrefix("https://s/json/stations/byuuid?uuids=2e6fabb2"))
    #expect(popularURL(server: "s", country: "PL").absoluteString.hasSuffix("limit=40&countrycode=PL"))
    #expect(!popularURL(server: "s", country: nil).absoluteString.contains("countrycode"))
}

private func suggestFetch(popularOK: Bool = true, recommendedOK: Bool = true) -> (URL) async throws -> Any {
    { url in
        if url.absoluteString.contains("byuuid") {
            if !recommendedOK { throw Down() }
            return [["name": "K", "url": "http://k", "stationuuid": recommendedIDs[3]],
                    ["name": "Dead", "url": "http://d", "stationuuid": recommendedIDs[0], "lastcheckok": 0],
                    ["name": "P", "url": "http://p", "stationuuid": recommendedIDs[2]]]
        }
        if !popularOK { throw Down() }
        return [["name": "Pop", "url": "http://pop"], ["name": "Down", "url": "http://dn", "lastcheckok": 0]]
    }
}

@Test func suggestionsOrderAndFilters() async throws {
    let (recommended, popular) = try await suggestions(country: "PL", bans: .none, fetch: suggestFetch())
    #expect(recommended.map(\.name) == ["P", "K"])
    #expect(popular.map(\.name) == ["Pop"])
}

@Test func suggestionsPopularFailureAndTotalFailure() async throws {
    let (recommended, popular) = try await suggestions(country: nil, bans: .none, fetch: suggestFetch(popularOK: false))
    #expect(recommended.count == 2 && popular.isEmpty)
    await #expect(throws: DirectoryError.unavailable) {
        _ = try await suggestions(country: nil, bans: .none, fetch: suggestFetch(popularOK: false, recommendedOK: false))
    }
}

@Test func bannedStationRules() {
    #expect(isHidden(banned("Radio Republika", "PL", "https://ssl-1.radiotvrepublika.pl:12698/stream"), bans: bans))
    #expect(isHidden(banned("Republika", "PL", "http://example.com/live"), bans: bans))
    #expect(isHidden(banned("X", "DE", "http://example.com/x", uuid: "F837704E-40DF-4302-B546-C8401348E51C"), bans: bans))
    #expect(isHidden(banned("X", "", "http://a.b.tvrepublika.pl/x"), bans: bans))
    #expect(!isHidden(banned("Dominikánská Republika", "CZ", "http://example.com/a"), bans: bans))
    #expect(!isHidden(banned("Republika ni Juan 87.5", "PH", "http://example.com/b"), bans: bans))
}

@Test func bannedStationFilteredFromResultsAndPopular() {
    let item: [String: Any] = ["name": "Radio Republika", "countrycode": "PL", "url": "https://ssl-1.radiotvrepublika.pl:12698/stream"]
    let other: [String: Any] = ["name": "Dominikánská Republika", "countrycode": "CZ", "url": "http://example.com/a"]
    #expect(parseResults([item, other], bans: bans).map(\.name) == ["Dominikánská Republika"])
    let hidden = banned("Radio Republika", "PL", "https://ssl-1.radiotvrepublika.pl:12698/stream")
    let otherEntry = banned("Other", "PL", "http://o/x")
    #expect(cleanPopular([hidden, otherEntry], recommended: [], bans: bans) == [otherEntry])
}

@Test func malformedOrMissingBanFileHidesNothing() throws {
    let folder = tempFolder()
    let bad = folder.appendingPathComponent("bad.json")
    try Data("{not json".utf8).write(to: bad)
    let hidden = banned("Radio Republika", "PL", "https://ssl-1.radiotvrepublika.pl/stream")
    #expect(!isHidden(hidden, bans: BanList.load(bad)))
    #expect(!isHidden(hidden, bans: BanList.load(folder.appendingPathComponent("missing.json"))))
}
