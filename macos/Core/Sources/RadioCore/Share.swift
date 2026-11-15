import Foundation

// Share a station: a link that opens a page on minimalistic-radio.github.io, which opens the radio with the station
// (docs/superpowers/specs/2026-11-15-share-station-design.md). The same rules as on Windows, Linux and the page.

/// A station from a share link, checked: a name of 1–100 characters, an http(s) address, an https logo or none.
public struct SharedStation: Equatable, Sendable {
    public let name: String
    public let url: String
    public let logo: String?

    public init(name: String, url: String, logo: String?) {
        self.name = name
        self.url = url
        self.logo = logo
    }
}

/// What a share link holds: a station, or nothing usable ("This link doesn't contain a station.").
public enum ShareLink: Equatable, Sendable {
    case station(SharedStation)
    case invalid
}

public let shareWebPrefix = "https://minimalistic-radio.github.io/#"
public let shareAppPrefix = "minimalistic-radio://add?"
let shareHost = "minimalistic-radio.github.io"
let shareScheme = "minimalistic-radio"
let shareMaxAddress = 2048
let shareMaxName = 100

/// n=name&u=address(&l=logo), form-encoded as the page's URLSearchParams writes it.
public func shareQuery(_ station: Station) -> String {
    var query = "n=" + formEncode(station.name) + "&u=" + formEncode(station.url)
    if let logo = station.logo, !logo.isEmpty { query += "&l=" + formEncode(logo) }
    return query
}

/// The link to send: the page, which offers to open the radio.
public func shareLink(_ station: Station) -> String {
    shareWebPrefix + shareQuery(station)
}

/// The link the page opens: straight into the radio.
public func shareAppLink(_ station: Station) -> String {
    shareAppPrefix + shareQuery(station)
}

/// A pasted or opened web link or app link: its station, `.invalid`, or nil when the text isn't a share link at all
/// (a search, a stream address).
public func readShareLink(_ text: String) -> ShareLink? {
    let link = text.trimmingCharacters(in: .whitespacesAndNewlines)
    let lowered = link.lowercased()
    let query: Substring
    if lowered.hasPrefix(shareScheme + ":") {
        // minimalistic-radio://add?… (or minimalistic-radio:add?…)
        var rest = link.dropFirst(shareScheme.count + 1)
        while rest.hasPrefix("/") { rest = rest.dropFirst() }
        let action = rest.prefix { $0 != "?" && $0 != "/" && $0 != "#" }
        guard action.lowercased() == "add", let mark = rest.firstIndex(of: "?") else { return .invalid }
        query = rest[rest.index(after: mark)...].prefix { $0 != "#" }
    } else if let afterHost = ["https://", "http://"].lazy.compactMap({ webRest(link, lowered, $0) }).first {
        // https://minimalistic-radio.github.io/#… (the part after # never reaches a server)
        guard let mark = afterHost.firstIndex(of: "#") else { return .invalid }
        query = afterHost[afterHost.index(after: mark)...]
    } else {
        return nil
    }
    let values = formDecode(query)
    guard let station = sharedStation(name: values["n"], url: values["u"], logo: values["l"]) else { return .invalid }
    return .station(station)
}

/// What follows "https://minimalistic-radio.github.io" when the link is on that host exactly.
private func webRest(_ link: String, _ lowered: String, _ scheme: String) -> Substring? {
    let start = scheme + shareHost
    guard lowered.hasPrefix(start) else { return nil }
    let rest = link.dropFirst(start.count)
    guard rest.isEmpty || "/#?".contains(rest.first!) else { return nil }   // not minimalistic-radio.github.io.example.com
    return rest
}

/// The link's values, checked as the spec says; nil when the name or the address is missing or bad.
func sharedStation(name: String?, url: String?, logo: String?) -> SharedStation? {
    guard let address = url?.trimmingCharacters(in: .whitespacesAndNewlines), address.count <= shareMaxAddress,
          isWebURL(address) else { return nil }
    var visible = String.UnicodeScalarView()
    visible.append(contentsOf: (name ?? "").trimmingCharacters(in: .whitespacesAndNewlines).unicodeScalars
        .filter { !CharacterSet.controlCharacters.contains($0) })
    let cleaned = String(String(visible).prefix(shareMaxName)).trimmingCharacters(in: .whitespacesAndNewlines)
    guard !cleaned.isEmpty else { return nil }
    let picture = logo?.trimmingCharacters(in: .whitespacesAndNewlines)
    let goodLogo = picture.flatMap { $0.count <= shareMaxAddress && isWebURL($0)
        && URLComponents(string: $0)?.scheme?.lowercased() == "https" ? $0 : nil }
    return SharedStation(name: cleaned, url: address, logo: goodLogo)
}

/// "Already on the list": the same address after trimming, the scheme and host in any case, the rest exactly, and
/// one trailing / either way.
public func sameStationAddress(_ a: String, _ b: String) -> Bool {
    matchKey(a) == matchKey(b)
}

private func matchKey(_ address: String) -> String {
    var text = address.trimmingCharacters(in: .whitespacesAndNewlines)
    if text.hasSuffix("/") { text.removeLast() }
    guard let separator = text.range(of: "://") else { return text }
    let scheme = text[..<separator.lowerBound].lowercased()
    let rest = text[separator.upperBound...]
    let hostEnd = rest.firstIndex { "/?#".contains($0) } ?? rest.endIndex
    return scheme + "://" + rest[..<hostEnd].lowercased() + rest[hostEnd...]
}

// MARK: - application/x-www-form-urlencoded

private let formSafe = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789*-._ ")

/// As URLSearchParams: letters, digits and *-._ stay, a space is +, the rest is percent-encoded UTF-8.
func formEncode(_ text: String) -> String {
    (text.addingPercentEncoding(withAllowedCharacters: formSafe) ?? "").replacingOccurrences(of: " ", with: "+")
}

/// key → value; the first of a repeated key counts, values that don't decode are left out.
func formDecode(_ query: Substring) -> [String: String] {
    var values: [String: String] = [:]
    for pair in query.split(separator: "&", omittingEmptySubsequences: true) {
        let parts = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
        let decode = { (part: Substring) in part.replacingOccurrences(of: "+", with: " ").removingPercentEncoding }
        guard let key = decode(parts[0]), values[key] == nil,
              let value = decode(parts.count > 1 ? parts[1] : "") else { continue }
        values[key] = value
    }
    return values
}
