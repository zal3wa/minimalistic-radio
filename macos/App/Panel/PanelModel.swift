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
        /// A station from a share link, to add (and play); nil for a link without one.
        case shared(SharedStation?)
    }

    /// A short message over the bottom of the station list, for a moment.
    enum Pill: Equatable {
        /// After ⋯ › Share.
        case linkCopied
        /// A shared station that is already on the list, which isn't played (Play automatically was unchecked).
        case alreadyOnTheList
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
    /// The pictures show what an installed copy shows: no "Move … to Applications" note (the runner doesn't run the
    /// app from Applications).
    var picturesMode = false
    /// Where some buttons are, in points from the panel's top left (`hotspot(_:)`): for the demo pictures' cursor.
    var hotspots: [String: CGRect] = [:]
    /// "Link copied" or "Already on your list" over the stations, for a moment.
    @Published private(set) var pill: Pill?
    private var pillTimer: DispatchWorkItem?
    /// The station (its address) the list scrolls to when it shows: a shared station, added or already there.
    @Published var scrollTarget: String?

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

    /// Space plays and stops, except where a text field takes the typing (and on a shared station, which asks).
    var spacePlays: Bool {
        switch page {
        case .search, .station, .shared: return false
        default: return true
        }
    }

    // MARK: - Sharing

    /// ⋯ › Share: the station's link on the clipboard, and "Link copied" for about two seconds.
    func share(_ station: Station) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(shareLink(station), forType: .string)
        showPill(.linkCopied, for: 2)
    }

    var linkCopied: Bool { pill == .linkCopied }

    /// `seconds` nil keeps it (the pictures).
    func showPill(_ shown: Pill, for seconds: Double?) {
        pillTimer?.cancel()
        pill = shown
        guard let seconds else { return }
        let hide = DispatchWorkItem { [weak self] in self?.pill = nil }
        pillTimer = hide
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: hide)
    }

    func hidePill() {
        pillTimer?.cancel()
        pill = nil
    }

    /// A share link opened or pasted. A station already on the list follows the saved "Play automatically": it
    /// plays, or the list shows it with "Already on your list" and nothing changes. Any other asks on the Shared
    /// station page; a link without a station says so there.
    func openShared(_ link: StationLink) {
        switch link {
        case .station(let station):
            switch controller.openShared(station) {
            case .playing(let index): showOnList(index)
            case .onTheList(let index): showOnList(index, pill: .alreadyOnTheList)
            case .ask: page = .shared(station)
            }
        case .invalid:
            page = .shared(nil)
        }
    }

    /// Text typed or pasted into an add-station field: true when it was a share link, now open. `complete`: the
    /// text was submitted, so a link without a station shows its message too (while typing, only a whole station
    /// opens, so a link typed by hand doesn't jump away half-way).
    func openSharedText(_ text: String, complete: Bool) -> Bool {
        guard let link = readShareLink(text), complete || link != .invalid else { return false }
        openShared(link)
        return true
    }

    /// Shared station › Add: added at the end (playing if `play`, Play automatically), and back to the stations
    /// scrolled to it. A stream the list already has under another address isn't added: unplayed, it says so.
    func addShared(_ station: SharedStation, play: Bool) {
        switch controller.addShared(station, play: play) {
        case .added(let index): showOnList(index)
        case .alreadyOnTheList(let index): showOnList(index, pill: play ? nil : .alreadyOnTheList)
        case .invalid: page = .stations
        }
    }

    /// The stations page, scrolled so the station at `index` shows, with `pill` for about three seconds.
    private func showOnList(_ index: Int, pill shown: Pill? = nil) {
        scrollTarget = controller.stations.indices.contains(index) ? controller.stations[index].url : nil
        page = .stations
        if let shown { showPill(shown, for: 3) }
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
}
