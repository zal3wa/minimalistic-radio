import Foundation
import Testing
@testable import RadioCore

// Share a station (docs/superpowers/specs/2026-11-15-share-station-design.md): building and reading the links, their
// validation, and matching a shared address to a station on the list.

private let hard = Station(name: "Antyradio Hard", url: "https://an05.cdn.eurozet.pl/ANTHAR.mp3")

// MARK: - Building

@Test func webLinkIsTheSpecExample() {
    #expect(shareLink(hard) == "https://minimalistic-radio.github.io/#n=Antyradio+Hard&u=https%3A%2F%2Fan05.cdn.eurozet.pl%2FANTHAR.mp3")
    #expect(shareAppLink(hard) == "minimalistic-radio://add?n=Antyradio+Hard&u=https%3A%2F%2Fan05.cdn.eurozet.pl%2FANTHAR.mp3")
}

@Test func logoIsAddedOnlyWhenThereIsOne() {
    let withLogo = Station(name: "B", url: "http://b.example/live", logo: "https://b.example/logo.png")
    #expect(shareLink(withLogo).hasSuffix("&l=https%3A%2F%2Fb.example%2Flogo.png"))
    #expect(!shareLink(hard).contains("&l="))
}

@Test func encodingIsWhatURLSearchParamsWrites() {
    // Letters, digits and *-._ stay; a space is +; everything else is percent-encoded UTF-8 (+ and & too).
    let odd = Station(name: "Rock & Roll + Jazz *-._ Świat", url: "http://x.example/a?b=1&c=2")
    #expect(shareQuery(odd) == "n=Rock+%26+Roll+%2B+Jazz+*-._+%C5%9Awiat&u=http%3A%2F%2Fx.example%2Fa%3Fb%3D1%26c%3D2")
}

// MARK: - Reading

@Test func roundTripsBothLinks() {
    let station = Station(name: "Rock & Roll + Jazz Świat", url: "http://x.example/a?b=1&c=2", logo: "https://x.example/l.png")
    let expected = ShareLink.station(SharedStation(name: station.name, url: station.url, logo: station.logo))
    #expect(readShareLink(shareLink(station)) == expected)
    #expect(readShareLink(shareAppLink(station)) == expected)
    #expect(readShareLink("  " + shareLink(station) + "\n") == expected)     // pasted with spaces around
}

@Test func plusAndPercentTwentyAreBothSpaces() {
    let plus = readShareLink("minimalistic-radio://add?n=Radio+357&u=https%3A%2F%2Fstream.radio357.pl%2F")
    let twenty = readShareLink("minimalistic-radio://add?n=Radio%20357&u=https://stream.radio357.pl/")
    let expected = ShareLink.station(SharedStation(name: "Radio 357", url: "https://stream.radio357.pl/", logo: nil))
    #expect(plus == expected)
    #expect(twenty == expected)
}

@Test func unknownKeysAreIgnoredAndTheFirstValueCounts() {
    let link = readShareLink("https://minimalistic-radio.github.io/#v=2&n=A&u=http%3A%2F%2Fa.example%2F1&n=B&x=y")
    #expect(link == .station(SharedStation(name: "A", url: "http://a.example/1", logo: nil)))
}

@Test(arguments: [
    "https://minimalistic-radio.github.io/#u=http%3A%2F%2Fa.example%2F1",                  // no name
    "https://minimalistic-radio.github.io/#n=A",                                           // no address
    "https://minimalistic-radio.github.io/#n=+++&u=http%3A%2F%2Fa.example%2F1",            // a name of spaces
    "https://minimalistic-radio.github.io/#n=A&u=ftp%3A%2F%2Fa.example%2F1",               // not http(s)
    "https://minimalistic-radio.github.io/#n=A&u=%2Flive",                                 // not absolute
    "https://minimalistic-radio.github.io/#n=A&u=javascript%3Aalert(1)",
    "https://minimalistic-radio.github.io/",                                               // nothing after #
    "https://minimalistic-radio.github.io",
    "minimalistic-radio://add",
    "minimalistic-radio://remove?n=A&u=http%3A%2F%2Fa.example%2F1",                        // not "add"
])
func invalidLinks(link: String) {
    #expect(readShareLink(link) == .invalid)
}

@Test func addressLongerThan2048IsInvalid() {
    let long = "http://a.example/" + String(repeating: "x", count: 2048 - 17)
    #expect(long.count == 2048)
    let ok = "minimalistic-radio://add?n=A&u=" + long
    #expect(readShareLink(ok) == .station(SharedStation(name: "A", url: long, logo: nil)))
    #expect(readShareLink(ok + "x") == .invalid)
}

@Test func nameIsCleanedAndCutTo100() {
    let long = String(repeating: "ab", count: 80)
    let link = readShareLink("minimalistic-radio://add?u=http%3A%2F%2Fa.example&n=%20%20" + long + "%0A")
    guard case .station(let station)? = link else { Issue.record("not a station: \(String(describing: link))"); return }
    #expect(station.name == String(long.prefix(100)))
    let controls = readShareLink("minimalistic-radio://add?u=http%3A%2F%2Fa.example&n=Ra%07dio%0D%0A%09Z%C5%82ote")
    guard case .station(let cleaned)? = controls else { Issue.record("not a station"); return }
    #expect(cleaned.name == "RadioZłote")
}

@Test func badLogoIsDroppedSilently() {
    let base = "minimalistic-radio://add?n=A&u=http%3A%2F%2Fa.example%2F1&l="
    let expected = ShareLink.station(SharedStation(name: "A", url: "http://a.example/1", logo: nil))
    #expect(readShareLink(base + "http%3A%2F%2Fa.example%2Flogo.png") == expected)          // not https
    #expect(readShareLink(base + "logo.png") == expected)
    #expect(readShareLink(base + "https%3A%2F%2Fa.example%2F" + String(repeating: "x", count: 2040)) == expected)
    #expect(readShareLink(base + "https%3A%2F%2Fa.example%2Flogo.png")
            == .station(SharedStation(name: "A", url: "http://a.example/1", logo: "https://a.example/logo.png")))
}

@Test(arguments: [
    "jazz",
    "Radio 357",
    "https://stream.radio357.pl/",
    "https://example.com/#n=A&u=http%3A%2F%2Fa.example%2F1",
    "https://minimalistic-radio.github.io.example.com/#n=A&u=http%3A%2F%2Fa.example%2F1",
    "",
])
func otherTextIsNotAShareLink(text: String) {
    #expect(readShareLink(text) == nil)
}

@Test func linksAreRecognisedWhateverTheCase() {
    let expected = ShareLink.station(SharedStation(name: "A", url: "http://a.example/1", logo: nil))
    #expect(readShareLink("HTTPS://Minimalistic-Radio.GitHub.io/#n=A&u=http%3A%2F%2Fa.example%2F1") == expected)
    #expect(readShareLink("Minimalistic-Radio://ADD?n=A&u=http%3A%2F%2Fa.example%2F1") == expected)
    #expect(readShareLink("https://minimalistic-radio.github.io/index.html#n=A&u=http%3A%2F%2Fa.example%2F1") == expected)
}

// MARK: - Matching

@Test(arguments: [
    ("https://an05.cdn.eurozet.pl/ANTHAR.mp3", "https://an05.cdn.eurozet.pl/ANTHAR.mp3", true),
    ("HTTPS://AN05.CDN.Eurozet.PL/ANTHAR.mp3", "https://an05.cdn.eurozet.pl/ANTHAR.mp3", true),   // scheme and host
    ("https://stream.radio357.pl/", "https://stream.radio357.pl", true),                          // one trailing /
    ("  https://stream.radio357.pl  ", "https://stream.radio357.pl", true),                         // trimmed
    ("https://an05.cdn.eurozet.pl/anthar.mp3", "https://an05.cdn.eurozet.pl/ANTHAR.mp3", false),  // the path exactly
    ("http://an05.cdn.eurozet.pl/ANTHAR.mp3", "https://an05.cdn.eurozet.pl/ANTHAR.mp3", false),   // another scheme
    ("https://x.example/a//", "https://x.example/a", false),                                       // only one /
    ("https://x.example/a?b=1", "https://x.example/a?B=1", false),
])
func matching(a: String, b: String, same: Bool) {
    #expect(sameStationAddress(a, b) == same)
    #expect(sameStationAddress(b, a) == same)
}

// MARK: - The controller

@MainActor @Test func knownStationJustPlays() {
    let r = Rig.started(), c = r.controller
    let shared = SharedStation(name: "Whatever", url: B.url.uppercased().replacingOccurrences(of: "/LIVE", with: "/live") + "/", logo: nil)
    #expect(c.playIfKnown(shared))
    #expect(c.current == 1 && c.status == .connecting && r.player.calls.last == .play(B.url))
    #expect(c.stations == [A, B, C])
    #expect(!c.playIfKnown(SharedStation(name: "New", url: "http://new.example/live", logo: nil)))
}

@MainActor @Test func addAndPlayAppendsAndPlays() {
    let r = Rig.started(), c = r.controller
    playing(c, 0)
    let shared = SharedStation(name: "New", url: "http://new.example/live", logo: "https://new.example/logo.png")
    #expect(c.addAndPlay(shared))
    #expect(c.stations.last == Station(name: "New", url: "http://new.example/live", logo: "https://new.example/logo.png"))
    #expect(c.current == 3 && c.status == .connecting && r.player.calls.last == .play("http://new.example/live"))
    #expect(r.savedNames == ["Alpha", "Beta", "Gamma", "New"])
}

@MainActor @Test func addAndPlayWithNothingPlayingStarts() {
    let r = Rig.started(), c = r.controller
    #expect(c.addAndPlay(SharedStation(name: "New", url: "http://new.example/live", logo: nil)))
    #expect(c.current == 3 && c.status == .connecting && r.player.calls.last == .play("http://new.example/live"))
}

@MainActor @Test func addAndPlayOfANearDuplicatePlaysTheOneOnTheList() {
    // https:// instead of http:// is another address for the link, but the same stream for the list.
    let r = Rig.started(), c = r.controller
    #expect(c.addAndPlay(SharedStation(name: "Alpha again", url: "https://a.example/live", logo: nil)))
    #expect(c.stations.count == 3 && c.current == 0 && r.player.calls.last == .play(A.url))
}
