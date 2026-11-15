import Foundation

// Song titles from stream metadata: a port of linux/minimalistic_radio/core/titles.py (the Windows ParseTrack).

public let radio357URL = URL(string: "https://stream.radio357.pl/now/playing.json")!

private let richPattern = try! NSRegularExpression(pattern: #"^title="([^"]*)",artist="([^"]*)""#)
private let artworkPattern = try! NSRegularExpression(pattern: #"amgArtworkURL="([^"]+)""#)
private let titleField = #" - text=""#

public func stationKind(_ url: String) -> String {
    let host = (URLComponents(string: url)?.host ?? "").lowercased()
    switch host {
    case "stream.revma.ihrhls.com": return "iheart"
    case "stream.radio357.pl": return "radio357"
    default: return "generic"
    }
}

private func has(_ text: String, _ part: String) -> Bool {
    text.range(of: part, options: .caseInsensitive) != nil
}

private func group(_ match: NSTextCheckingResult, _ index: Int, in text: String) -> String {
    guard let range = Range(match.range(at: index), in: text) else { return "" }
    return String(text[range])
}

public func parseTitle(_ raw: String?, kind: String) -> String? {
    guard let raw, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
    var value = htmlUnescape(raw).trimmingCharacters(in: .whitespacesAndNewlines)
    if kind == "iheart" {
        let whole = NSRange(value.startIndex..., in: value)
        if let rich = richPattern.firstMatch(in: value, range: whole) {
            let title = group(rich, 1, in: value).trimmingCharacters(in: .whitespaces)
            let artist = group(rich, 2, in: value).trimmingCharacters(in: .whitespaces)
            if title.isEmpty || artist.isEmpty { return nil }
            value = artist + " – " + title
        } else if has(value, "song_spot=") || has(value, #"text=""#) {
            let lowered = value.lowercased()
            guard let separator = lowered.range(of: titleField), separator.lowerBound > lowered.startIndex,
                  has(value, #"song_spot="M""#),
                  let end = lowered.range(of: #"" song_spot="#, range: separator.upperBound..<lowered.endIndex),
                  end.lowerBound > separator.upperBound else { return nil }
            // `lowered` has the same length as `value` here (ASCII field names), so the offsets carry over.
            let artistEnd = lowered.distance(from: lowered.startIndex, to: separator.lowerBound)
            let titleStart = lowered.distance(from: lowered.startIndex, to: separator.upperBound)
            let titleEnd = lowered.distance(from: lowered.startIndex, to: end.lowerBound)
            let characters = Array(value)
            guard titleEnd <= characters.count else { return nil }
            value = String(characters[0..<artistEnd]) + " – " + String(characters[titleStart..<titleEnd])
        }
    }
    let lowered = value.lowercased()
    if lowered.hasPrefix("radio 357") || lowered.hasPrefix("radio nowy świat - pion i poziom")
        || !value.contains(where: { $0.isLetter || $0.isNumber }) {
        return nil
    }
    return value.count > 240 ? String(value.prefix(240)) + "…" : value
}

public func artworkFromRaw(_ raw: String?) -> String? {
    guard let raw else { return nil }
    guard let match = artworkPattern.firstMatch(in: raw, range: NSRange(raw.startIndex..., in: raw)) else { return nil }
    let address = group(match, 1, in: raw)
    return isWebURL(address) ? address : nil
}

/// "Artist – Title" → (artist, title); without a separator the whole text is the title.
public func splitTrack(_ track: String?) -> (artist: String?, title: String?) {
    guard let track, !track.isEmpty else { return (nil, track) }
    for separator in [" – ", " — ", " - "] {
        if let range = track.range(of: separator), range.lowerBound > track.startIndex, range.upperBound < track.endIndex {
            return (String(track[..<range.lowerBound]).trimmingCharacters(in: .whitespaces),
                    String(track[range.upperBound...]).trimmingCharacters(in: .whitespaces))
        }
    }
    return (nil, track)
}

public func radio357Title(_ payload: Any?) -> String? {
    (payload as? [String: Any])?["s"] as? String
}

/// The HTML entities stations put in titles: named basics and numeric ones (as WebUtility.HtmlDecode on Windows).
func htmlUnescape(_ text: String) -> String {
    guard text.contains("&") else { return text }
    let named = ["amp": "&", "lt": "<", "gt": ">", "quot": "\"", "apos": "'", "nbsp": "\u{00A0}"]
    var result = ""
    var rest = Substring(text)
    while let amp = rest.firstIndex(of: "&") {
        result += rest[..<amp]
        let after = rest[rest.index(after: amp)...]
        if let semicolon = after.prefix(10).firstIndex(of: ";") {
            let name = String(after[..<semicolon])
            var replacement: String?
            if name.hasPrefix("#x") || name.hasPrefix("#X"), let code = UInt32(name.dropFirst(2), radix: 16) {
                replacement = Unicode.Scalar(code).map { String(Character($0)) }
            } else if name.hasPrefix("#"), let code = UInt32(name.dropFirst()) {
                replacement = Unicode.Scalar(code).map { String(Character($0)) }
            } else {
                replacement = named[name]
            }
            if let replacement {
                result += replacement
                rest = after[after.index(after: semicolon)...]
                continue
            }
        }
        result += "&"
        rest = after
    }
    return result + rest
}
