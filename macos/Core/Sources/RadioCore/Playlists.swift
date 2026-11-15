import Foundation

// Station playlists (.pls, .m3u): AVPlayer can't play them, so the player plays their first stream.
// A port of linux/minimalistic_radio/audio/playlists.py.

private let playlistTypes: Set<String> = ["audio/x-scpls", "audio/x-mpegurl", "audio/mpegurl"]
private let plsEntry = try! NSRegularExpression(pattern: #"^file(\d+)\s*=\s*(.*)$"#, options: [.caseInsensitive])

/// The address names a playlist file. .m3u8 is HLS, which AVPlayer plays itself.
public func isPlaylistURL(_ url: String) -> Bool {
    let path = (URLComponents(string: url)?.path ?? "").lowercased()
    return path.hasSuffix(".pls") || path.hasSuffix(".m3u")
}

/// The server's Content-Type says playlist (parameters such as charset are ignored).
public func isPlaylistType(_ contentType: String?) -> Bool {
    let type = (contentType ?? "").split(separator: ";", maxSplits: 1, omittingEmptySubsequences: false).first ?? ""
    return playlistTypes.contains(type.trimmingCharacters(in: .whitespaces).lowercased())
}

/// An HLS playlist (served as audio/mpegurl, which Apple allows): AVPlayer plays it, not its first line.
public func isHLS(_ text: String) -> Bool {
    text.contains("#EXT-X-")
}

/// The first http(s) stream of a .pls or .m3u playlist, relative entries resolved against `baseURL`.
public func firstStream(_ text: String, baseURL: String) -> String? {
    var body = Substring(text)
    while body.first == "\u{FEFF}" { body = body.dropFirst() }
    let lines = body.components(separatedBy: .newlines).map { $0.trimmingCharacters(in: .whitespaces) }
    var entries: [(Int, String)] = []
    for line in lines {
        let range = NSRange(line.startIndex..., in: line)
        if let match = plsEntry.firstMatch(in: line, range: range),
           let numberRange = Range(match.range(at: 1), in: line), let valueRange = Range(match.range(at: 2), in: line),
           let number = Int(line[numberRange]) {
            entries.append((number, line[valueRange].trimmingCharacters(in: .whitespaces)))
        }
    }
    let candidates: [String]
    if !entries.isEmpty || lines.contains(where: { $0.lowercased() == "[playlist]" }) {
        candidates = entries.sorted { $0.0 < $1.0 }.map { $0.1 }
    } else {
        candidates = lines.filter { !$0.isEmpty && !$0.hasPrefix("#") }
    }
    let base = URL(string: baseURL)
    for entry in candidates {
        guard let resolved = URL(string: entry, relativeTo: base)?.absoluteString else { continue }
        if isWebURL(resolved) { return resolved }
    }
    return nil
}
