import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_playlists.py.

@Test func plsFirstFile() {
    #expect(firstStream("[playlist]\nFile1=http://a/s\n", baseURL: "http://x/p.pls") == "http://a/s")
}

@Test func plsLowestNumberWins() {
    let text = "[playlist]\r\nNumberOfEntries=2\r\nFile2=http://b/s\r\nTitle2=B\r\nFile1=http://a/s\r\nVersion=2\r\n"
    #expect(firstStream(text, baseURL: "http://x/p.pls") == "http://a/s")
}

@Test func m3uSkipsComments() {
    #expect(firstStream("#EXTM3U\n#EXTINF:-1,Radio\n\nhttp://a/s\nhttp://b/s\n", baseURL: "http://x/p.m3u") == "http://a/s")
}

@Test func m3uReturnsFirstHttpLine() {
    #expect(firstStream("rtsp://a/s\nC:\\Music\\song.mp3\nhttps://b/s\n", baseURL: "http://x/p.m3u") == "https://b/s")
}

@Test func relativeEntriesResolveAgainstBaseURL() {
    #expect(firstStream("live/stream.mp3\n", baseURL: "http://x/dir/p.m3u") == "http://x/dir/live/stream.mp3")
    #expect(firstStream("[playlist]\nFile1=/live\n", baseURL: "https://x/dir/p.pls") == "https://x/live")
}

@Test func byteOrderMarkIsIgnored() {
    #expect(firstStream("\u{FEFF}http://a/s\n", baseURL: "http://x/p.m3u") == "http://a/s")
    #expect(firstStream("\u{FEFF}[playlist]\nFile1=http://a/s\n", baseURL: "http://x/p.pls") == "http://a/s")
}

@Test func emptyPlaylistIsNil() {
    for text in ["", "\n\n", "#EXTM3U\n", "[playlist]\nNumberOfEntries=0\n", "ftp://a/s\n"] {
        #expect(firstStream(text, baseURL: "http://x/p.m3u") == nil, "\(text)")
    }
}

@Test func playlistURLByPath() {
    #expect(isPlaylistURL("http://x/a.pls") && isPlaylistURL("https://x/A.M3U?id=1"))
    for url in ["http://x/a.m3u8", "http://x/a.mp3", "http://x/stream", "http://x/?f=a.pls", ""] {
        #expect(!isPlaylistURL(url), "\(url)")
    }
}

@Test func playlistContentTypes() {
    for value in ["audio/x-scpls", "Audio/X-MPEGURL; charset=utf-8", "audio/mpegurl"] {
        #expect(isPlaylistType(value), "\(value)")
    }
    for value: String? in ["audio/mpeg", "application/vnd.apple.mpegurl", "audio/aacp", "", nil] {
        #expect(!isPlaylistType(value), "\(value ?? "nil")")
    }
}

@Test func hlsIsNotAStationPlaylist() {
    #expect(isHLS("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nseg1.aac\n"))
    #expect(isHLS("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=64000\nlow/index.m3u8\n"))
    #expect(!isHLS("#EXTM3U\n#EXTINF:-1,Radio\nhttp://a/s\n"))
}
