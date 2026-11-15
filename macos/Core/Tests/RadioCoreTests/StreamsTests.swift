import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_streams.py.

@Test func streamKeyIgnoresSchemeCaseDefaultPortAndTrailingSlash() {
    #expect(streamKey("HTTP://Example.COM:80/live/") == "example.com/live")
    #expect(streamKey("https://example.com:443/live") == "example.com/live")
    #expect(streamKey("http://example.com:8000/live") == "example.com:8000/live")
    #expect(streamKey("https://example.com/live?x=1") == "example.com/live?x=1")
    #expect(streamKey("  not a url ") == "not a url")
}

@Test func sameStreamCompares() {
    #expect(sameStream("http://a.com/s", "https://A.com/s/"))
    #expect(!sameStream("http://a.com/s", "http://a.com/t"))
}

@Test func isWebURLAcceptsOnlyHttpWithAHost() {
    #expect(isWebURL("http://x.com/a") && isWebURL("https://x.com"))
    for bad: String? in [nil, "", "example.com", "ftp://x.com", "https://user:pw@x.com/", "file:///tmp/x"] {
        #expect(!isWebURL(bad), "\(bad ?? "nil")")
    }
}
