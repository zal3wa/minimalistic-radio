import RadioCore
import SwiftUI

/// The panel: the top bar, the page, and on the stations page the player at the bottom.
struct PanelView: View {
    @ObservedObject var model: PanelModel

    var body: some View {
        VStack(spacing: 0) {
            HeaderView(model: model)
            PanelDivider()
            if !inApplications && !model.picturesMode {
                Text(L("Move Minimalistic Radio to Applications to get updates."))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
                    .background(Color.yellow.opacity(0.15))
            }
            Group {
                switch model.page {
                case .stations: StationsPage(model: model)
                case .station(let index): StationForm(model: model, index: index)
                case .search: SearchPage(model: model)
                case .history: HistoryPage(model: model)
                case .settings: SettingsPage(model: model)
                case .statistics: StatisticsPage(model: model)
                case .shared(let station): SharedStationPage(model: model, station: station)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .overlay(alignment: .bottom) {
                if let pill = model.pill, model.page == .stations {
                    MessagePill(text: pill == .linkCopied ? L("Link copied") : L("Already on your list"))
                        .padding(.bottom, 12)
                        .transition(.opacity)
                }
            }
            .animation(.easeInOut(duration: 0.2), value: model.pill)
            if model.page == .stations {
                PanelDivider()
                FooterView(model: model)
            }
        }
        .frame(width: PanelController.size.width, height: PanelController.size.height)
        .coordinateSpace(name: Hotspots.space)
        .onPreferenceChange(Hotspots.self) { model.hotspots = $0 }
        .background {
            // The radio has no menu bar of its own: ⌘Q quits it, ⌘W hides the panel, and Space plays and stops on
            // every page without a text field (the Play/Stop button is only on the stations page).
            ZStack {
                Button("") { NSApp.terminate(nil) }.keyboardShortcut("q", modifiers: .command)
                Button("") { model.close() }.keyboardShortcut("w", modifiers: .command)
                Button("") { model.controller.toggle() }.keyboardShortcut(model.spacePlays ? KeyboardShortcut(.space, modifiers: []) : nil)
            }
            .opacity(0)
        }
    }

    /// Updates need the app in Applications (not run from the DMG or Downloads).
    private var inApplications: Bool {
        let path = Bundle.main.bundlePath
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return (path.hasPrefix("/Applications/") || path.hasPrefix(home + "/Applications/")) && !path.contains("/AppTranslocation/")
            || Bundle.main.object(forInfoDictionaryKey: "MRReleaseTag") as? String == "dev"
    }
}

/// The frames of the views marked with `hotspot(_:)`, in the panel's coordinates (points from its top left).
struct Hotspots: PreferenceKey {
    static let space = "panel"
    static var defaultValue: [String: CGRect] { [:] }

    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) {
        value.merge(nextValue()) { $1 }
    }
}

extension View {
    /// Reports this view's frame as `name` (the demo pictures' cursor goes there).
    func hotspot(_ name: String) -> some View {
        background(GeometryReader { space in
            Color.clear.preference(key: Hotspots.self, value: [name: space.frame(in: .named(Hotspots.space))])
        })
    }
}

/// The 1 pt line under the top bar and above the player: the text colour at 10 %.
struct PanelDivider: View {
    var body: some View {
        Rectangle().fill(Color.primary.opacity(0.1)).frame(height: 1)
    }
}

/// The panel's top bar. On the stations page: [+ Station] [History], then the green update button while an update
/// is ready, and Settings. On the other pages: ‹ and the page's title, and on Song history [Statistics] on the right.
/// The panel hides with a click elsewhere, Esc, ⌘W or the menu bar icon, so there is no close button.
struct HeaderView: View {
    @ObservedObject var model: PanelModel

    var body: some View {
        HStack(spacing: 6) {
            if model.page == .stations {
                Button { model.addStation() } label: { Label(L("Station"), systemImage: "plus") }
                    .help(L("Add a station"))
                    .buttonStyle(.bordered)
                    .keyboardShortcut("f", modifiers: .command)
                Button { model.page = .history } label: {
                    // The clock is taller than the plus: a size smaller keeps both buttons 24 pt high.
                    Label { Text(L("History")) } icon: { Image(systemName: "clock.arrow.circlepath").imageScale(.medium) }
                }
                .help(L("Song history"))
                .buttonStyle(.bordered)
                .hotspot("history")
                Spacer()
                if let update = model.updateLabel {
                    iconButton(help: update, action: { AppDelegate.shared?.updater?.install() }) {
                        Image(systemName: "arrow.down.circle.fill")
                            .symbolRenderingMode(.palette)
                            .foregroundStyle(.white, .green)
                    }
                }
                iconButton(help: L("Settings"), action: { model.page = .settings }) {
                    Image(systemName: "gearshape")
                }
                .keyboardShortcut(",", modifiers: .command)
            } else {
                iconButton(help: L("Back"), action: { model.back() }) {
                    Image(systemName: "chevron.left")
                }
                .hotspot("back")
                .padding(.trailing, -2)
                Text(title)
                    .font(.system(size: 13, weight: .bold))
                    .lineLimit(1)
                Spacer()
                if model.page == .history {
                    Button { model.openStatistics() } label: {
                        Label { Text(L("Statistics")) } icon: { Image(systemName: "chart.bar").imageScale(.medium) }
                    }
                    .buttonStyle(.bordered)
                    .hotspot("statistics")
                }
            }
        }
        .imageScale(.large)
        // Equal space above, below and left of [+ Station] (24 pt high in a 44 pt bar); the subpages' ‹ sits in a
        // 26 pt box, so it starts 2 pt further left.
        .padding(.leading, model.page == .stations ? 10 : 8)
        .padding(.trailing, 10)
        .frame(height: 44)
    }

    /// An icon in a 26 pt box (as in the mockups), so the buttons on the right end 10 pt from the edge.
    private func iconButton<Icon: View>(help: String, action: @escaping () -> Void,
                                        @ViewBuilder icon: () -> Icon) -> some View {
        Button(action: action) {
            icon()
                .frame(width: 26, height: 26)
                .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .help(help)
    }

    private var title: String {
        switch model.page {
        case .stations: return L("Stations")
        case .search: return L("Add a station")
        case .history: return L("Song history")
        case .settings: return L("Settings")
        case .statistics: return L("Statistics")
        case .shared: return L("Shared station")
        case .station(let index): return index == nil ? L("Add by address") : L("Edit")
        }
    }
}

/// "Link copied" after ⋯ › Share, or "Already on your list" after a link to a station on it: a pill in the menus'
/// colours over the bottom of the list, just above the player.
struct MessagePill: View {
    let text: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .symbolRenderingMode(.palette)
                .foregroundStyle(.white, .green)
                .font(.system(size: 18))
            Text(text)
        }
        .padding(.leading, 10)
        .padding(.trailing, 16)
        .frame(height: 36)
        .background {
            Capsule()
                .fill(Color(nsColor: Self.menuBackground))
                .overlay(Capsule().strokeBorder(Color.primary.opacity(0.16), lineWidth: 0.5))
                .shadow(color: .black.opacity(0.18), radius: 9, y: 6)
        }
        .accessibilityElement(children: .combine)
    }

    /// The menus' background: light grey, or dark grey in the dark look.
    private static let menuBackground = NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            ? NSColor(srgbRed: 0x2C / 255, green: 0x2C / 255, blue: 0x2E / 255, alpha: 1)
            : NSColor(srgbRed: 0xEC / 255, green: 0xEC / 255, blue: 0xEC / 255, alpha: 1)
    }
}
