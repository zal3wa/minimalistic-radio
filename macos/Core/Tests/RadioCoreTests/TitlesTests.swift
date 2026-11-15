import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_titles.py.

@Test(arguments: [
    (#"Sienna Spiro - text="Great Expectation" song_spot="M""#, "iheart", "Sienna Spiro – Great Expectation"),
    (#"title="The Way",artist="ARIANA GRANDE / MAC MILLER",url="song_spot=\"F\"""#, "iheart", "ARIANA GRANDE / MAC MILLER – The Way"),
    (#"title="",artist="",url="""#, "iheart", nil),
    ("Radio 357 - Najlepszy radiowy adres na świecie!", "radio357", nil),
    ("The Streets - Blinded by the Lights", "generic", "The Streets - Blinded by the Lights"),
    (#"Promo - text="Reklama" song_spot="A""#, "iheart", nil),
    (#"- text="Spot Block End" amgTrackId="9876543" length="00:00:00""#, "iheart", nil),
    ("Simon &amp; Garfunkel - Mrs. Robinson", "generic", "Simon & Garfunkel - Mrs. Robinson"),
    ("Radio Nowy Świat - Pion i poziom", "generic", nil),
    (" --- ", "generic", nil),
] as [(String, String, String?)])
func parseTitleCases(raw: String, kind: String, expected: String?) {
    #expect(parseTitle(raw, kind: kind) == expected)
}

@Test func parseTitleOfNothing() {
    #expect(parseTitle(nil, kind: "generic") == nil)
}

@Test func longTitleCutAt240() {
    #expect(parseTitle(String(repeating: "A", count: 300), kind: "generic") == String(repeating: "A", count: 240) + "…")
}

@Test func stationKindByHost() {
    #expect(stationKind("https://stream.radio357.pl/?s=www") == "radio357")
    #expect(stationKind("http://stream.revma.ihrhls.com/zc185") == "iheart")
    #expect(stationKind("http://rs6.rmf.pl/rmf_fm") == "generic")
}

@Test func splitTrackFindsArtistAndTitle() {
    #expect(splitTrack("Leonard Cohen - Everybody Knows") == ("Leonard Cohen", "Everybody Knows"))
    #expect(splitTrack("Dżingiel") == (nil, "Dżingiel"))
    #expect(splitTrack("A – B") == ("A", "B"))
}

@Test func artworkFromRawNeedsAWebAddress() {
    #expect(artworkFromRaw(#"x amgArtworkURL="https://i.iheart.com/a.jpg" y"#) == "https://i.iheart.com/a.jpg")
    #expect(artworkFromRaw(#"amgArtworkURL="javascript:x""#) == nil)
}

@Test func radio357TitleFromItsFeed() {
    #expect(radio357Title(["s": "Kult - Arahja"]) == "Kult - Arahja")
    #expect(radio357Title([Any]()) == nil)
}
