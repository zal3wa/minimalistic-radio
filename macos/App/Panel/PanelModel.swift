import AppKit
import RadioCore
import SwiftUI

/// What the panel shows. The controller isn't observable, so this republishes its changes to SwiftUI and keeps
/// the panel's own state: the page, the station being edited.
@MainActor
final class PanelModel: ObservableObject {
    enum Page: Equatable {
        case stations
        case search
        case history
        case settings
        /// Opened from Settings, and back to it.
        case statistics
        /// Add (nil) or edit (the station's index) a station by its address.
        case station(Int?)
    }

    let controller: RadioController
    let logos: LogoCache
    /// Stations never shown in search or suggestions (data/banned-stations.json, in the app).
    let bans = BanList.load(Bundle.main.url(forResource: "banned-stations", withExtension: "json")
                            ?? URL(fileURLWithPath: "/nonexistent"))
    /// The suggestions, loaded once per opening of the panel.
    var suggested: (recommended: [DirectoryStation], popular: [DirectoryStation], country: String?)?
    @Published var page: Page = .stations
    /// A search to run when the search page opens (the README pictures' "jazz").
    @Published var pendingSearch: String?
    /// The last search's results, once they arrived.
    var lastResults: [DirectoryStation]?
    @Published private(set) var revision = 0
    /// Set by the panel controller: hides the panel.
    var close: () -> Void = {}
    /// For the pictures (--screenshot): sample statistics instead of the real ones (nothing is saved), and the
    /// update button and the Updates settings as a release shows them.
    var sampleStatistics: StatisticsLog?
    var sampleUpdate: String?
    var showsUpdatesAlways = false

    init(controller: RadioController, logos: LogoCache) {
        self.controller = controller
        self.logos = logos
        controller.subscribe { [weak self] _ in self?.revision += 1 }
    }

    /// Redraws everything (a language change, the update arrow).
    func refresh() {
        revision += 1
    }

    /// + Station: the search page with its suggestions ("Add by address" is a link there), as on Windows.
    func addStation() {
        page = .search
    }

    /// Space plays and stops, except where a text field takes the typing.
    var spacePlays: Bool {
        switch page {
        case .search, .station: return false
        default: return true
        }
    }

    /// The page Statistics was opened from (Song history or Settings): where ‹ and Esc take it back.
    private(set) var statisticsFrom = Page.settings

    /// Statistics, from Song history's [Statistics] or Settings › Statistics › Show.
    func openStatistics() {
        statisticsFrom = page == .history ? .history : .settings
        page = .statistics
    }

    /// Where ‹ and Esc go: Statistics back to where it was opened from, every other page to the stations.
    var parent: Page {
        page == .statistics ? statisticsFrom : .stations
    }

    /// Esc: back a page, or closes the panel on the stations.
    func back() {
        if page == .stations { close() } else { page = parent }
    }

    /// The green update button's tooltip, while an update is ready.
    var updateLabel: String? {
        sampleUpdate ?? AppDelegate.shared?.updater?.label
    }

    var showsUpdates: Bool {
        showsUpdatesAlways || AppDelegate.shared?.updater?.enabled == true
    }

    /// The statistics as they are now (the running session up to this moment).
    var statistics: StatisticsLog {
        sampleStatistics ?? controller.statisticsNow
    }

    /// The station on the list for a history entry or a statistics row: by address, then by name.
    func station(url: String? = nil, name: String) -> Station? {
        if let url, let byAddress = controller.stations.first(where: { sameStream($0.url, url) }) { return byAddress }
        return controller.stations.first { $0.name == name }
    }
}
