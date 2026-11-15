import AppKit
import RadioCore
import SwiftUI
import UniformTypeIdentifiers

/// Settings, as on Windows, in the Mac's grouped style: language, open at login, the station card, the station
/// list's export and import, updates, about, quit.
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
                    HStack {
                        Button(L("Export…"), action: exportStations)
                        Button(L("Import…"), action: importStations)
                    }
                } label: {
                    Text(L("Station list"))
                    Text(listMessage ?? L("A copy in a file, e.g. for friends"))
                }
            }
            if AppDelegate.shared?.updater?.enabled == true {
                Section(L("Updates")) {
                    Toggle(isOn: Binding(get: { controller.prefs.checkUpdates }, set: { controller.setCheckUpdates($0) })) {
                        Text(L("Updates"))
                        Text(L("Looks for a new version every few hours"))
                    }
                    LabeledContent {
                        Button(L("Check now"), action: checkNow)
                    } label: {
                        Text(updateMessage ?? lastCheck)
                    }
                }
            }
            Section(L("About")) {
                LabeledContent(appName, value: version)
                Link("github.com/zal3wa/minimalistic-radio", destination: URL(string: "https://github.com/zal3wa/minimalistic-radio")!)
                Text("MIT License").foregroundStyle(.secondary)
            }
            Section {
                Button(L("Quit Minimalistic Radio"), role: .destructive) { NSApp.terminate(nil) }
            }
        }
        .formStyle(.grouped)
        .onAppear { openAtLogin = LoginItem.isEnabled }
    }

    private var version: String {
        let tag = Bundle.main.object(forInfoDictionaryKey: "MRReleaseTag") as? String ?? "dev"
        return tag.hasPrefix("macos-v") ? String(tag.dropFirst(7)) : appVersion
    }

    private var lastCheck: String {
        guard let last = controller.prefs.lastUpdateCheck else { return L("Not checked yet.") }
        return DateFormatter.localizedString(from: last, dateStyle: .short, timeStyle: .short)
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
        guard run(dialog), let url = dialog.url else { return }
        listMessage = controller.exportStations(url)
            ? L("Stations saved: {0}.").replacingOccurrences(of: "{0}", with: String(controller.stations.count))
            : L("Couldn't save the file.")
    }

    private func importStations() {
        let dialog = NSOpenPanel()
        dialog.allowedContentTypes = [.json]
        guard run(dialog), let url = dialog.url else { return }
        let result = controller.importStations(url)
        if let error = result.error {
            listMessage = error
        } else if result.added == 0 {
            listMessage = L("All stations from this file are already on the list.")
        } else {
            listMessage = L("Stations added: {0}.").replacingOccurrences(of: "{0}", with: String(result.added))
        }
    }

    /// A file dialog: the panel stays open behind it.
    private func run(_ dialog: NSSavePanel) -> Bool {
        let panel = AppDelegate.shared?.panel
        panel?.keepOpen = true
        defer { panel?.keepOpen = false }
        return dialog.runModal() == .OK
    }

    private func checkNow() {
        updateMessage = L("Checking…")
        AppDelegate.shared?.updater?.checkNow { result in updateMessage = result }
    }
}
