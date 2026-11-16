import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_covers.py.

@Test func itunesURL() {
    #expect(itunesSearchURL("Leonard Cohen - Everybody Knows")?.absoluteString
            == "https://itunes.apple.com/search?media=music&entity=song&limit=5&term=Leonard%20Cohen%20Everybody%20Knows")
    #expect(itunesSearchURL("Dżingiel") == nil)
}

@Test func sameArtistMatchesTheFirstArtist() {
    #expect(sameArtist("ARIANA GRANDE / MAC MILLER", "Ariana Grande"))
    #expect(!sameArtist("Queen", "Abba"))
    #expect(!sameArtist("A", "A"))
}

@Test func pickCoverNeedsMatchingArtist() {
    let payload: [String: Any] = ["results": [
        ["artistName": "Someone Else", "artworkUrl100": "https://x/100x100bb.jpg"],
        ["artistName": "Leonard Cohen", "artworkUrl100": "https://y/100x100bb.jpg"],
    ]]
    #expect(pickCover(artist: "Leonard Cohen", payload: payload) == "https://y/600x600bb.jpg")
    #expect(pickCover(artist: "Leonard Cohen", payload: ["results": [Any]()]) == nil)
}

@Test func coverLookupFailureNotCached() {
    let cache = CoverCache()
    #expect(cache.get("A - B") == (false, nil))
    cache.put("A - B", nil)   // "no cover" is cached; a network failure is simply never put
    #expect(cache.get("A - B") == (true, nil))
}

@Test func pickCoverNeedsAWebAddress() {
    for picture in ["file:///etc/100x100bb.jpg", "javascript:alert(1)//100x100bb.jpg", "100x100bb.jpg", "ftp://x/100x100bb.jpg"] {
        let payload: [String: Any] = ["results": [["artistName": "Leonard Cohen", "artworkUrl100": picture]]]
        #expect(pickCover(artist: "Leonard Cohen", payload: payload) == nil)
    }
    let payload: [String: Any] = ["results": [
        ["artistName": "Leonard Cohen", "artworkUrl100": "file:///etc/100x100bb.jpg"],
        ["artistName": "Leonard Cohen", "artworkUrl100": "https://y/100x100bb.jpg"],
    ]]
    #expect(pickCover(artist: "Leonard Cohen", payload: payload) == "https://y/600x600bb.jpg")
}
