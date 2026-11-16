import Foundation

// A port of linux/minimalistic_radio/core/storage.py: the same files and JSON shapes, kept in the Mac's folders.

public let supportedLanguageSettings = ["auto", "pl", "en", "de", "uk", "cs", "es", "fr", "it", "pt"]
public let historyLimit = 100

public struct Paths: Equatable, Sendable {
    public let support: URL
    public let cache: URL

    public init(support: URL, cache: URL) {
        self.support = support
        self.cache = cache
    }

    /// ~/Library/Application Support/Minimalistic Radio and ~/Library/Caches/io.github.zal3wa.minimalistic-radio.
    public static func standard() -> Paths {
        let files = FileManager.default
        let support = files.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let caches = files.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        return Paths(support: support.appendingPathComponent("Minimalistic Radio"),
                     cache: caches.appendingPathComponent("io.github.zal3wa.minimalistic-radio"))
    }

    public var stationsFile: URL { support.appendingPathComponent("stations.json") }
    public var preferencesFile: URL { support.appendingPathComponent("preferences.json") }
    public var historyFile: URL { support.appendingPathComponent("history.json") }
    public var statisticsFile: URL { support.appendingPathComponent("statistics.json") }
    public var logosFolder: URL { cache.appendingPathComponent("logos") }
    public var coversFolder: URL { cache.appendingPathComponent("covers") }
}

struct CorruptFile: Error {}

/// Parsed JSON; nil when the file is missing. Throws CorruptFile when it can't be read as JSON (a UTF-8 BOM is fine).
func readJSON(_ url: URL) throws -> Any? {
    guard FileManager.default.fileExists(atPath: url.path) else { return nil }
    guard var body = try? Data(contentsOf: url) else { throw CorruptFile() }
    if body.starts(with: [0xEF, 0xBB, 0xBF]) { body = body.dropFirst(3) }
    guard let value = try? JSONSerialization.jsonObject(with: body, options: [.fragmentsAllowed]) else {
        throw CorruptFile()
    }
    return value
}

/// Written whole or not at all: a temporary file, then a rename.
func writeJSON(_ url: URL, _ value: Any) throws {
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    let data = try JSONSerialization.data(withJSONObject: value, options: [.withoutEscapingSlashes])
    try data.write(to: url, options: .atomic)
}

public func loadStations(_ url: URL) -> (stations: [Station], wasCorrupt: Bool) {
    let data: Any?
    do {
        data = try readJSON(url)
    } catch {
        moveAside(url)
        return ([], true)
    }
    guard let data else { return ([], false) }
    guard let items = data as? [Any] else {
        moveAside(url)
        return ([], true)
    }
    var stations: [Station] = []
    for case let item as [String: Any] in items {
        let name = cleanName(item["Name"] as? String)
        guard !name.isEmpty, let address = item["Url"] as? String, isWebURL(address) else { continue }
        stations.append(Station(name: name, url: address, logo: item["Logo"] as? String))
    }
    return (stations, false)
}

/// Keeps only the `keep` newest files of a cache folder (covers, logos), so it doesn't grow without end.
func pruneFolder(_ folder: URL, keep: Int) {
    let files = FileManager.default
    let keys: [URLResourceKey] = [.contentModificationDateKey, .isRegularFileKey]
    guard let entries = try? files.contentsOfDirectory(at: folder, includingPropertiesForKeys: keys) else { return }
    let dated: [(Date, URL)] = entries.compactMap { url in
        guard let values = try? url.resourceValues(forKeys: Set(keys)), values.isRegularFile == true else { return nil }
        return (values.contentModificationDate ?? .distantPast, url)
    }
    for (_, url) in dated.sorted(by: { $0.0 > $1.0 }).dropFirst(keep) {
        try? files.removeItem(at: url)
    }
}

func moveAside(_ url: URL) {
    let bad = url.deletingLastPathComponent().appendingPathComponent(url.lastPathComponent + ".bad")
    try? FileManager.default.removeItem(at: bad)
    try? FileManager.default.moveItem(at: url, to: bad)
}

public func saveStations(_ url: URL, _ stations: [Station]) throws {
    let items: [[String: Any]] = stations.map { station in
        ["Name": station.name, "Url": station.url, "Logo": station.logo ?? NSNull()]
    }
    try writeJSON(url, items)
}

public func loadPreferences(_ url: URL) -> Preferences {
    var prefs = Preferences()
    guard let data = (try? readJSON(url)) as? [String: Any] else { return prefs }
    if let volume = data["Volume"] as? NSNumber, !isBool(volume) {
        prefs.volume = max(0, min(100, volume.intValue))
    }
    if let last = data["LastPlayed"] as? String { prefs.lastPlayed = last }
    if let language = data["Language"] as? String, supportedLanguageSettings.contains(language) {
        prefs.language = language
    }
    if let value = data["ShowStationPopup"] as? NSNumber, isBool(value) { prefs.showStationPopup = value.boolValue }
    if let value = data["CheckUpdates"] as? NSNumber, isBool(value) { prefs.checkUpdates = value.boolValue }
    if let value = data["UpdateByDownload"] as? NSNumber, isBool(value) { prefs.updateByDownload = value.boolValue }
    if let value = data["CollectStatistics"] as? NSNumber, isBool(value) { prefs.collectStatistics = value.boolValue }
    if let value = data["PlaySharedStations"] as? NSNumber, isBool(value) { prefs.playSharedStations = value.boolValue }
    if let text = data["LastUpdateCheck"] as? String { prefs.lastUpdateCheck = parseTime(text) }
    return prefs
}

public func savePreferences(_ url: URL, _ prefs: Preferences) throws {
    let data: [String: Any] = [
        "Volume": prefs.volume,
        "LastPlayed": prefs.lastPlayed ?? NSNull(),
        "Language": prefs.language,
        "ShowStationPopup": prefs.showStationPopup,
        "CheckUpdates": prefs.checkUpdates,
        "LastUpdateCheck": prefs.lastUpdateCheck.map(formatTime) ?? NSNull(),
        "UpdateByDownload": prefs.updateByDownload,
        "CollectStatistics": prefs.collectStatistics,
        "PlaySharedStations": prefs.playSharedStations,
    ]
    try writeJSON(url, data)
}

public func loadHistory(_ url: URL) -> [HistoryEntry] {
    guard let items = (try? readJSON(url)) as? [Any] else { return [] }
    var entries: [HistoryEntry] = []
    for case let item as [String: Any] in items {
        guard let title = item["Title"] as? String, let station = item["Station"] as? String,
              let text = item["Time"] as? String, let time = parseTime(text) else { continue }
        entries.append(HistoryEntry(title: title, station: station, time: time))
    }
    return Array(entries.prefix(historyLimit))
}

public func saveHistory(_ url: URL, _ entries: [HistoryEntry]) throws {
    let items: [[String: Any]] = entries.prefix(historyLimit).map { entry in
        ["Title": entry.title, "Station": entry.station, "Time": formatTime(entry.time)]
    }
    try writeJSON(url, items)
}

/// JSON booleans come back as NSNumber too; this tells them apart from numbers.
func isBool(_ number: NSNumber) -> Bool {
    CFGetTypeID(number) == CFBooleanGetTypeID()
}

/// Local time to the second, as Linux writes it ("2026-11-14T19:52:00").
private func timeFormatter() -> DateFormatter {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = .current
    formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
    return formatter
}

func formatTime(_ date: Date) -> String {
    timeFormatter().string(from: date)
}

/// Local time ("2026-11-14T19:52:00"), or with a zone ("...Z", "...+01:00").
func parseTime(_ text: String) -> Date? {
    if let date = timeFormatter().date(from: text) { return date }
    return ISO8601DateFormatter().date(from: text)
}
