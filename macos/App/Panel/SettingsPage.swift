import AppKit
import RadioCore
import SwiftUI
import UniformTypeIdentifiers

/// Settings, the same on every system, in the Mac's grouped style: General (language, open at login, the station
/// card), Stations (export and import), Statistics, Updates, About, Quit.
struct SettingsPage: View {
    @ObservedObject var model: PanelModel
    @State private var listMessage: String?
    @State private var updateMessage: String?
    @State private var openAtLogin = LoginItem.isEnabled

    private var controller: RadioController { model.controller }

    /// The languages under their own names, as on Windows.
    private let languages: [(code: String, name: String)] = [
        ("pl", "Polski"), ("en", "English"), ("de", "Deutsch"), ("uk", "Українська"), ("cs", "Čeština"),
        ("es", "Español"), ("fr", "Français"), ("it", "Italiano"), ("pt", "Português"),
    ]

    var body: some View {
        Form {
            Section(L("General")) {
                Picker(L("Language"), selection: Binding(get: { controller.prefs.language },
                                                         set: { controller.setLanguage($0) })) {
                    Text(L("Same as system")).tag("auto")
                    ForEach(languages, id: \.code) { Text($0.name).tag($0.code) }
                }
                Toggle(isOn: Binding(get: { openAtLogin }, set: setOpenAtLogin)) {
                    Text(L("Open at login"))
                    Text(L("Waits by the clock, doesn't play by itself"))
                }
                Toggle(isOn: Binding(get: { controller.prefs.showStationPopup }, set: { controller.setShowStationPopup($0) })) {
                    Text(L("Show station changes"))
                    Text(L("A card under the icon after a media key or menu switch"))
                }
            }
            Section(L("Stations")) {
                LabeledContent {
                    EmptyView()
                } label: {
                    Text(L("Station list"))
                    Text(listMessage ?? L("A copy in a file, e.g. for friends"))
                }
                HStack {
                    Spacer()
                    Button(L("Export…"), action: exportStations)
                    Button(L("Import…"), action: importStations)
                }
            }
            Section {
                Toggle(isOn: Binding(get: { controller.prefs.collectStatistics },
                                     set: { controller.setCollectStatistics($0) })) {
                    Text(L("Statistics"))
                    Text(L("Collected only on this computer, never sent anywhere"))
                }
                LabeledContent {
                    Button(L("Show")) { model.openStatistics() }
                } label: {
                    Text(collectedSince).font(.subheadline).foregroundStyle(.secondary)
                }
            }
            if model.showsUpdates {
                Section(L("Updates")) {
                    Toggle(isOn: Binding(get: { controller.prefs.checkUpdates }, set: { controller.setCheckUpdates($0) })) {
                        Text(L("Automatic updates"))
                        Text(L("Looks for a new version every few hours"))
                    }
                    LabeledContent {
                        Button(L("Check now"), action: checkNow)
                    } label: {
                        Text(updateMessage ?? lastCheck).font(.subheadline).foregroundStyle(.secondary)
                    }
                }
            }
            Section(L("About")) {
                HStack(spacing: 10) {
                    // The icon itself: the system's application icon is drawn inside a grey tile on macOS 26.
                    Image(nsImage: NSImage(named: "AppIcon") ?? NSApp.applicationIconImage)
                        .resizable()
                        .interpolation(.high)
                        .frame(width: 38, height: 38)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(appName)
                        Text(L("Version {0}").replacingOccurrences(of: "{0}", with: version) + " · MIT")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 4)
                    Link(destination: URL(string: "https://github.com/zal3wa/minimalistic-radio")!) {
                        HStack(spacing: 2) {
                            Text("GitHub")
                            Image(systemName: "arrow.up.right").imageScale(.small)
                        }
                    }
                    .help("github.com/zal3wa/minimalistic-radio")
                }
            }
            Section {
                LabeledContent {
                    Button(role: .destructive) { NSApp.terminate(nil) } label: {
                        Text(L("Quit")).foregroundStyle(.red)
                    }
                } label: {
                    Text(L("Quit"))
                    Text(L("Stops the radio and removes it from the menu bar"))
                }
            }
        }
        .formStyle(.grouped)
        .onAppear { openAtLogin = LoginItem.isEnabled }
    }

    private var version: String {
        let tag = Bundle.main.object(forInfoDictionaryKey: "MRReleaseTag") as? String ?? "dev"
        return tag.hasPrefix("macos-v") ? String(tag.dropFirst(7)) : appVersion
    }

    /// "Collected since 2 March 2025" (the first session's day, the UI language's long date), or "Nothing collected yet".
    private var collectedSince: String {
        guard let since = model.statistics.since else { return L("Nothing collected yet") }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: localizer.language)
        formatter.dateStyle = .long
        formatter.timeStyle = .none
        return L("Collected since {0}").replacingOccurrences(of: "{0}", with: formatter.string(from: since))
    }

    private var lastCheck: String {
        guard let last = controller.prefs.lastUpdateCheck else { return L("Not checked yet.") }
        return L("Last checked: {0}").replacingOccurrences(
            of: "{0}", with: DateFormatter.localizedString(from: last, dateStyle: .short, timeStyle: .short))
    }

    private func setOpenAtLogin(_ on: Bool) {
        try? LoginItem.set(on)
        if LoginItem.needsApproval { LoginItem.openSettings() }
        openAtLogin = LoginItem.isEnabled
    }

    private func exportStations() {
        let dialog = NSSavePanel()
        dialog.nameFieldStringValue = "stations.json"
        dialog.allowedContentTypes = [.json]
        run(dialog) { url in
            listMessage = controller.exportStations(url)
                ? L("Stations saved: {0}.").replacingOccurrences(of: "{0}", with: String(controller.stations.count))
                : L("Couldn't save the file.")
        }
    }

    private func importStations() {
        let dialog = NSOpenPanel()
        dialog.allowedContentTypes = [.json]
        run(dialog) { url in
            let result = controller.importStations(url)
            if let error = result.error {
                listMessage = error
            } else if result.added == 0 {
                listMessage = L("All stations from this file are already on the list.")
            } else {
                listMessage = L("Stations added: {0}.").replacingOccurrences(of: "{0}", with: String(result.added))
            }
        }
    }

    /// A file dialog as a sheet on the panel, so it is never under it, and the panel stays open behind it.
    private func run(_ dialog: NSSavePanel, _ done: @escaping (URL) -> Void) {
        guard let window = AppDelegate.shared?.panel?.window else {
            if dialog.runModal() == .OK, let url = dialog.url { done(url) }
            return
        }
        dialog.beginSheetModal(for: window) { response in
            if response == .OK, let url = dialog.url { done(url) }
        }
    }

    private func checkNow() {
        updateMessage = L("Checking…")
        AppDelegate.shared?.updater?.checkNow { result in updateMessage = result }
    }
}
