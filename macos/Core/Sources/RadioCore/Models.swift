import Foundation

/// A saved station. In stations.json: {"Name", "Url", "Logo"}, as on Windows and Linux.
public struct Station: Equatable, Hashable, Sendable {
    public var name: String
    public var url: String
    public var logo: String?

    public init(name: String, url: String, logo: String? = nil) {
        self.name = name
        self.url = url
        self.logo = logo
    }
}

/// preferences.json: Volume, LastPlayed, Language, ShowStationPopup, CheckUpdates, LastUpdateCheck, UpdateByDownload,
/// CollectStatistics.
public struct Preferences: Equatable, Sendable {
    public var volume = 30
    public var lastPlayed: String?
    public var language = "auto"
    public var showStationPopup = true
    public var checkUpdates = true
    public var lastUpdateCheck: Date?
    /// This Mac couldn't replace the app in place, so updates are offered as a DMG to drag.
    public var updateByDownload = false
    /// Settings › Statistics: off, nothing new goes into statistics.json (what is there stays).
    public var collectStatistics = true
    /// The shared-station page's "Play automatically": checked the first time, then the choice made with the last Add.
    public var playSharedStations = true

    public init() {}
}

/// A song in the history: history.json holds {"Title", "Station", "Time"}.
public struct HistoryEntry: Equatable, Sendable {
    public var title: String
    public var station: String
    public var time: Date

    public init(title: String, station: String, time: Date) {
        self.title = title
        self.station = station
        self.time = time
    }
}
