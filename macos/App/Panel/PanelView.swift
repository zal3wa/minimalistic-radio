import RadioCore
import SwiftUI

/// The panel: the header, the page, and the player at the bottom (as on Windows).
struct PanelView: View {
    @ObservedObject var model: PanelModel

    var body: some View {
        VStack(spacing: 0) {
            HeaderView(model: model)
            if !inApplications {
                Text(L("Move Minimalistic Radio to Applications to get updates."))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
                    .background(Color.yellow.opacity(0.15))
            }
            Divider()
            Group {
                switch model.page {
                case .stations: StationsPage(model: model)
                case .station(let index): StationForm(model: model, index: index)
                case .search: SearchPage(model: model)
                case .history: HistoryPage(model: model)
                case .settings: SettingsPage(model: model)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            Divider()
            FooterView(model: model)
        }
        .frame(width: PanelController.size.width, height: PanelController.size.height)
        .background {
            // ⌘Q: the radio has no menu bar of its own, so the panel quits it.
            Button("") { NSApp.terminate(nil) }.keyboardShortcut("q", modifiers: .command).opacity(0)
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

/// The panel's top row: on the stations page the add, history and settings buttons; on the other pages a back
/// button and the page's title. Close and the green update arrow are on every page.
struct HeaderView: View {
    @ObservedObject var model: PanelModel

    var body: some View {
        HStack(spacing: 6) {
            if model.page == .stations {
                Button { model.page = .station(nil) } label: { Label(L("Station"), systemImage: "plus") }
                    .help(L("Add a station"))
                    .buttonStyle(.bordered)
                Button { model.page = .search } label: { Image(systemName: "magnifyingglass") }
                    .help(L("Search the radio-browser.info directory"))
                    .buttonStyle(.borderless)
                    .keyboardShortcut("f", modifiers: .command)
                Spacer()
            } else {
                Button { model.page = .stations } label: { Image(systemName: "chevron.left") }
                    .help(L("Back"))
                    .buttonStyle(.borderless)
                Text(title).font(.headline)
                Spacer()
            }
            if let update = AppDelegate.shared?.updater?.label {
                Button { AppDelegate.shared?.updater?.install() } label: {
                    Image(systemName: "arrow.down.circle.fill").foregroundStyle(.green)
                }
                .help(update)
                .buttonStyle(.borderless)
            }
            if model.page == .stations {
                Button { model.page = .history } label: { Image(systemName: "clock.arrow.circlepath") }
                    .help(L("Song history"))
                    .buttonStyle(.borderless)
                Button { model.page = .settings } label: { Image(systemName: "gearshape") }
                    .help(L("Settings"))
                    .buttonStyle(.borderless)
                    .keyboardShortcut(",", modifiers: .command)
            }
            Button { model.close() } label: { Image(systemName: "xmark") }
                .help(L("Hide the panel (the radio keeps playing)"))
                .buttonStyle(.borderless)
                .keyboardShortcut("w", modifiers: .command)
        }
        .imageScale(.large)
        .padding(.horizontal, 12)
        .frame(height: 44)
    }

    private var title: String {
        switch model.page {
        case .stations: return L("Stations")
        case .search: return L("Add a station")
        case .history: return L("Song history")
        case .settings: return L("Settings")
        case .station(let index): return index == nil ? L("Add by address") : L("Edit")
        }
    }
}
