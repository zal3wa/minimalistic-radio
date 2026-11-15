import Foundation

// radio-browser.info station search and suggestions: a port of linux/minimalistic_radio/core/directory.py,
// with the Windows playable filter (Storage.Playable in src/Services/Storage.cs), where the Mac also plays HLS.

public let directoryServers = ["de1.api.radio-browser.info", "nl1.api.radio-browser.info"]
public let popularShown = 15
private let searchAsked = 40     // like Windows: some are filtered out
private let searchShown = 30
private let popularAsked = 40

/// Our hand-picked stations (music), by radio-browser stationuuid so addresses and logos stay current.
public let recommendedIDs = [
    "2e6fabb2-9a10-4b2a-91ae-25a7d535e247",   // 102.7 KIIS FM Los Angeles
    "9245e3a5-bf69-4a08-8fac-3903a55043bf",   // Antyradio Hard
    "9617a958-0601-11e8-ae97-52543be04c81",   // Radio Paradise Main Mix
    "a509502d-1ba7-4d51-9791-0be5a7d5ec34",   // KEXP 90.3 Seattle
    "961e6cac-0601-11e8-ae97-52543be04c81",   // NTS Radio 1
    "c454908c-eb81-11e9-a96c-52543be04c81",   // FIP Groove
    "9625d631-0601-11e8-ae97-52543be04c81",   // Radio Swiss Jazz
    "9aa33d22-a6ef-11e9-a787-52543be04c81",   // Radio Swiss Classic
    "960cf833-0601-11e8-ae97-52543be04c81",   // SomaFM Groove Salad
    "960e4940-0601-11e8-ae97-52543be04c81",   // Ibiza Global Radio
]

public struct DirectoryStation: Equatable, Sendable {
    public var name: String
    public var country: String
    public var url: String
    public var logo: String?
    public var codec: String
    public var bitrate: Int
    public var tags: String
    public var id: String
    public var working: Bool
    public var countryCode: String
    public var hls: Bool

    public init(name: String, country: String, url: String, logo: String?, codec: String, bitrate: Int, tags: String,
                id: String = "", working: Bool = true, countryCode: String = "", hls: Bool = false) {
        self.name = name
        self.country = country
        self.url = url
        self.logo = logo
        self.codec = codec
        self.bitrate = bitrate
        self.tags = tags
        self.id = id
        self.working = working
        self.countryCode = countryCode
        self.hls = hls
    }
}

public enum DirectoryError: Error, Equatable {
    case unavailable
}

/// Stations that are never shown (data/banned-stations.json, shared with Windows and Linux).
public struct BanList: Equatable, Sendable {
    public var hosts: Set<String> = []
    public var uuids: Set<String> = []
    public var names: Set<String> = []   // "<country code>|<nameKey>"

    public static let none = BanList()

    public init() {}

    public init(json: Data) throws {
        var body = json
        if body.starts(with: [0xEF, 0xBB, 0xBF]) { body = body.dropFirst(3) }
        guard let root = try JSONSerialization.jsonObject(with: body) as? [String: Any],
              let stations = root["stations"] as? [[String: Any]] else { throw CorruptFile() }
        for station in stations {
            for host in station["hosts"] as? [String] ?? [] { hosts.insert(host.trimmingCharacters(in: .whitespaces).lowercased()) }
            for uuid in station["uuids"] as? [String] ?? [] { uuids.insert(uuid.trimmingCharacters(in: .whitespaces).lowercased()) }
            let country = String(describing: station["country"] ?? "").trimmingCharacters(in: .whitespaces).uppercased()
            if !country.isEmpty {
                for name in station["names"] as? [String] ?? [] { names.insert(country + "|" + nameKey(name)) }
            }
        }
    }

    /// The ban list in `url`; a missing or malformed file hides nothing.
    public static func load(_ url: URL) -> BanList {
        guard let data = try? Data(contentsOf: url), let bans = try? BanList(json: data) else { return .none }
        return bans
    }
}

private let unreserved = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

private func encode(_ text: String) -> String {
    text.addingPercentEncoding(withAllowedCharacters: unreserved) ?? ""
}

public func searchURL(server: String, query: String) -> URL {
    URL(string: "https://\(server)/json/stations/search?hidebroken=true&limit=\(searchAsked)"
        + "&order=clickcount&reverse=true&name=\(encode(query))")!
}

public func recommendedURL(server: String) -> URL {
    URL(string: "https://\(server)/json/stations/byuuid?uuids=\(recommendedIDs.joined(separator: ","))")!
}

public func popularURL(server: String, country: String?) -> URL {
    var text = "https://\(server)/json/stations/search?hidebroken=true&order=clickcount&reverse=true&limit=\(popularAsked)"
    if let country { text += "&countrycode=\(encode(country))" }
    return URL(string: text)!
}

/// What the Mac plays: MP3, AAC, AAC+ and unknown codecs (often MP3 or AAC after all), and HLS.
public func playable(codec: String?, hls: Bool) -> Bool {
    if hls { return true }
    switch (codec ?? "").trimmingCharacters(in: .whitespaces).uppercased() {
    case "MP3", "AAC", "AAC+", "UNKNOWN", "": return true
    default: return false
    }
}

private func text(_ item: [String: Any], _ key: String) -> String {
    item[key] as? String ?? ""
}

private func integer(_ value: Any?) -> Int? {
    guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
    return number.intValue
}

public func parseResults(_ items: Any?, limit: Int = 30, bans: BanList = .none) -> [DirectoryStation] {
    var seen: Set<String> = []
    var found: [DirectoryStation] = []
    for case let item as [String: Any] in items as? [Any] ?? [] {
        let resolved = text(item, "url_resolved"), address = isWebURL(resolved) ? resolved : text(item, "url")
        let name = text(item, "name")
        guard !name.trimmingCharacters(in: .whitespaces).isEmpty, isWebURL(address), !seen.contains(address) else { continue }
        let favicon = text(item, "favicon")
        let entry = DirectoryStation(
            name: name, country: text(item, "country"), url: address, logo: favicon.isEmpty ? nil : favicon,
            codec: text(item, "codec"), bitrate: integer(item["bitrate"]) ?? 0, tags: text(item, "tags"),
            id: text(item, "stationuuid"), working: integer(item["lastcheckok"]) != 0,
            countryCode: text(item, "countrycode").trimmingCharacters(in: .whitespaces).uppercased(),
            hls: integer(item["hls"]) == 1)
        if isHidden(entry, bans: bans) { continue }
        seen.insert(address)
        found.append(entry)
    }
    return Array(found.prefix(limit))
}

public func isHidden(_ entry: DirectoryStation, bans: BanList) -> Bool {
    if !entry.id.isEmpty && bans.uuids.contains(entry.id.lowercased()) { return true }
    var host = (URLComponents(string: entry.url)?.host ?? "").lowercased()
    while host.hasSuffix(".") { host.removeLast() }
    if bans.hosts.contains(where: { host == $0 || host.hasSuffix("." + $0) }) { return true }
    let key = nameKey(entry.name)   // "Radio" alone has no key: it never matches a name
    return !key.isEmpty && bans.names.contains(entry.countryCode.uppercased() + "|" + key)
}

public func subtitle(_ entry: DirectoryStation) -> String {
    var details: [String] = []
    let country = entry.country.trimmingCharacters(in: .whitespaces)
    if !country.isEmpty { details.append(country) }
    var format = entry.codec.trimmingCharacters(in: .whitespaces).uppercased()
    if format == "UNKNOWN" { format = "" }
    if entry.bitrate > 0 { format = "\(format) \(entry.bitrate) kbps".trimmingCharacters(in: .whitespaces) }
    if !format.isEmpty { details.append(format) }
    let genres = entry.tags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    if !genres.isEmpty { details.append(genres.prefix(2).joined(separator: ", ")) }
    return details.joined(separator: " · ")
}

public func toStation(_ entry: DirectoryStation) -> Station {
    Station(name: entry.name.trimmingCharacters(in: .whitespaces), url: entry.url,
            logo: isWebURL(entry.logo) ? entry.logo : nil)
}

/// One request to the first server that answers, then the second.
private func firstAnswer(_ urlFor: (String) -> URL, limit: Int, bans: BanList,
                         fetch: (URL) async throws -> Any) async throws -> [DirectoryStation] {
    for server in directoryServers {
        if let payload = try? await fetch(urlFor(server)) {
            return parseResults(payload, limit: limit, bans: bans)
        }
    }
    throw DirectoryError.unavailable
}

public func search(_ query: String, bans: BanList, fetch: (URL) async throws -> Any) async throws -> [DirectoryStation] {
    let found = try await firstAnswer({ searchURL(server: $0, query: query) }, limit: searchAsked, bans: bans, fetch: fetch)
    return Array(found.filter { playable(codec: $0.codec, hls: $0.hls) }.prefix(searchShown))
}

/// Names like "-- # TOP 100 CHARTS ---" or "a,b,c,d,e": starts with a symbol, has "||", "#" or "***", many commas.
public func looksLikeSpam(_ name: String?) -> Bool {
    let name = (name ?? "").trimmingCharacters(in: .whitespaces)
    guard let first = name.first else { return true }
    return !(first.isLetter || first.isNumber) || name.contains("||") || name.contains("#") || name.contains("***")
        || name.filter({ $0 == "," }).count > 3
}

/// Names compared loosely: "Radio RMF FM" and "RMF FM" are one station.
public func nameKey(_ name: String?) -> String {
    let words = (name ?? "").lowercased().split(whereSeparator: \.isWhitespace).filter { $0 != "radio" }
    return String(words.joined().filter { $0.isLetter || $0.isNumber })
}

/// Not already recommended, no duplicates by name or stream, no spam, the first `limit`.
public func cleanPopular(_ items: [DirectoryStation], recommended: [DirectoryStation], limit: Int = popularShown,
                         bans: BanList = .none) -> [DirectoryStation] {
    var names = Set(recommended.map { nameKey($0.name) })
    var streams = Set(recommended.map { streamKey($0.url) })
    var kept: [DirectoryStation] = []
    for entry in items {
        if looksLikeSpam(entry.name) || isHidden(entry, bans: bans) { continue }
        let key = nameKey(entry.name), stream = streamKey(entry.url)
        // A name that is nothing but "Radio" has an empty key: it is not compared by name.
        if (!key.isEmpty && names.contains(key)) || streams.contains(stream) { continue }
        if !key.isEmpty { names.insert(key) }
        streams.insert(stream)
        kept.append(entry)
        if kept.count == limit { break }
    }
    return kept
}

/// Where each of the radio's languages is spoken, its home country first. English keeps the system country.
private let languageCountries: [String: [String]] = [
    "pl": ["PL"],
    "de": ["DE", "AT", "CH", "LI", "LU"],
    "uk": ["UA"],
    "cs": ["CZ"],
    "es": ["ES", "MX", "AR", "CO", "CL", "PE", "VE", "EC", "GT", "CU", "BO", "DO", "HN", "PY", "SV", "NI",
           "CR", "PA", "UY", "PR"],
    "fr": ["FR", "BE", "CH", "LU", "MC", "CA"],
    "it": ["IT", "CH", "SM"],
    "pt": ["PT", "BR", "AO", "MZ"],
]

/// The system country if the language is spoken there, else the language's home country (nil: unknown).
public func countryFor(language: String, systemCountry: String?) -> String? {
    guard let countries = languageCountries[language] else { return systemCountry }
    if let systemCountry, countries.contains(systemCountry) { return systemCountry }
    return countries[0]
}

/// The language code ("pl") of the first entry of a list like ["pl-PL", "en"]; "en" for none.
public func languageOf(_ languages: [String]) -> String {
    guard let first = languages.first else { return "en" }
    return String(first.split(whereSeparator: { "_.@-".contains($0) }).first ?? "en").lowercased()
}

/// (recommended, popular). Throws `.unavailable` if both are empty. If only the popular request fails, the
/// recommended ones are still returned (and the popular list is empty).
public func suggestions(country: String?, bans: BanList,
                        fetch: (URL) async throws -> Any) async throws -> (recommended: [DirectoryStation], popular: [DirectoryStation]) {
    let fetched = try await firstAnswer({ recommendedURL(server: $0) }, limit: recommendedIDs.count, bans: bans, fetch: fetch)
    let byID = Dictionary(fetched.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
    let recommended = recommendedIDs.compactMap { byID[$0] }.filter { $0.working && playable(codec: $0.codec, hls: $0.hls) }
    var popular: [DirectoryStation] = []
    if let items = try? await firstAnswer({ popularURL(server: $0, country: country) }, limit: popularAsked, bans: bans, fetch: fetch) {
        popular = cleanPopular(items.filter { $0.working && playable(codec: $0.codec, hls: $0.hls) },
                               recommended: recommended, bans: bans)
    }
    if recommended.isEmpty && popular.isEmpty { throw DirectoryError.unavailable }
    return (recommended, popular)
}
