import Foundation

// Album art lookup helpers: a port of linux/minimalistic_radio/core/covers.py (the Windows Covers, without the HTTP).

private let unreserved = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

public func itunesSearchURL(_ track: String) -> URL? {
    let (artist, title) = splitTrack(track)
    guard let artist else { return nil }
    let term = "\(artist) \(title ?? "")".addingPercentEncoding(withAllowedCharacters: unreserved) ?? ""
    return URL(string: "https://itunes.apple.com/search?media=music&entity=song&limit=5&term=\(term)")
}

private func clean(_ text: String) -> String {
    String(text.lowercased().filter { $0.isLetter || $0.isNumber })
}

public func sameArtist(_ wanted: String, _ found: String?) -> Bool {
    guard let found, !found.isEmpty else { return false }
    // "ARIANA GRANDE / MAC MILLER": the first artist is enough.
    let firstArtist = wanted.split(maxSplits: 1, omittingEmptySubsequences: false,
                                   whereSeparator: { "/,&(;".contains($0) }).first.map(String.init) ?? wanted
    let first = clean(firstArtist)
    let other = clean(found)
    return first.count > 1 && other.count > 1 && (first.contains(other) || other.contains(first))
}

public func pickCover(artist: String, payload: Any?) -> String? {
    guard let results = (payload as? [String: Any])?["results"] as? [Any] else { return nil }
    for case let item as [String: Any] in results {
        if let picture = item["artworkUrl100"] as? String, let name = item["artistName"] as? String,
           sameArtist(artist, name) {
            return picture.replacingOccurrences(of: "100x100bb", with: "600x600bb")
        }
    }
    return nil
}

/// Remembers lookups, including "no cover". A failed lookup is simply never put.
public final class CoverCache {
    private var known: [String: String?] = [:]

    public init() {}

    public func get(_ track: String) -> (known: Bool, url: String?) {
        guard let entry = known[track] else { return (false, nil) }
        return (true, entry)
    }

    public func put(_ track: String, _ url: String?) {
        known[track] = .some(url)
    }
}
