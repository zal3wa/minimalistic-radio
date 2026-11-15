import RadioCore
import SwiftUI

/// Add a station: the radio-browser.info search, with suggestions while the box is empty (Recommended, then Popular
/// in your country or worldwide), and "Add by address".
struct SearchPage: View {
    @ObservedObject var model: PanelModel
    @State private var query = ""
    @State private var results: [DirectoryStation]?
    @State private var message: String?
    @FocusState private var focused: Bool

    private var controller: RadioController { model.controller }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                TextField(L("Type a station name"), text: $query)
                    .textFieldStyle(.roundedBorder)
                    .focused($focused)
                    .onSubmit(search)
                    .onChange(of: query) { text in
                        if text.trimmingCharacters(in: .whitespaces).isEmpty {
                            results = nil
                            message = nil
                        }
                    }
                Button(L("Search"), action: search)
            }
            HStack {
                Spacer()
                Button(L("Add by address")) { model.page = .station(nil) }
                    .buttonStyle(.link)
            }
            if let message {
                Text(message).foregroundStyle(.secondary).font(.callout)
            }
            List {
                if let results {
                    ForEach(results, id: \.url) { DirectoryRow(model: model, entry: $0, message: $message) }
                } else if let suggested = model.suggested {
                    if !suggested.recommended.isEmpty {
                        Section(L("Recommended")) {
                            ForEach(suggested.recommended, id: \.url) { DirectoryRow(model: model, entry: $0, message: $message) }
                        }
                    }
                    if !suggested.popular.isEmpty {
                        Section(suggested.country == nil ? L("Popular worldwide") : L("Popular in your country")) {
                            ForEach(suggested.popular, id: \.url) { DirectoryRow(model: model, entry: $0, message: $message) }
                        }
                    }
                }
            }
            .listStyle(.inset)
            .scrollContentBackground(.hidden)
            .panelScrollBars(model)
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .onAppear {
            focused = true
            runPending()
        }
        .onChange(of: model.pendingSearch) { _ in runPending() }
        .task { await loadSuggestions() }
    }

    private func runPending() {
        guard let pending = model.pendingSearch else { return }
        model.pendingSearch = nil
        query = pending
        search()
    }

    private func search() {
        let text = query.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        message = L("Searching…")
        results = []
        Task {
            do {
                let found = try await RadioCore.search(text, bans: model.bans, fetch: Network.json)
                guard query.trimmingCharacters(in: .whitespaces) == text else { return }   // typed on meanwhile
                results = found
                model.lastResults = found
                message = found.isEmpty ? L("No results.") : nil
            } catch {
                results = []
                model.lastResults = []
                message = L("The station directory is unavailable right now. Try again.")
            }
        }
    }

    /// Once per opening of the panel.
    private func loadSuggestions() async {
        guard model.suggested == nil else { return }
        message = L("Loading suggestions…")
        let country = countryFor(language: localizer.language, systemCountry: Locale.current.region?.identifier)
        do {
            let found = try await suggestions(country: country, bans: model.bans, fetch: Network.json)
            model.suggested = (found.recommended, found.popular, country)
            if results == nil { message = nil }
        } catch {
            if results == nil { message = L("The station directory is unavailable right now. Try again.") }
        }
    }
}

/// A station from the directory: logo, name, "country · codec bitrate · genres", and + (or ✓ when it is on the list).
struct DirectoryRow: View {
    @ObservedObject var model: PanelModel
    let entry: DirectoryStation
    @Binding var message: String?

    private var onList: Bool { model.controller.stations.contains { sameStream($0.url, entry.url) } }

    var body: some View {
        HStack(spacing: 12) {
            LogoView(logos: model.logos, url: entry.logo, size: 40)
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.name.trimmingCharacters(in: .whitespaces)).lineLimit(1)
                Text(subtitle(entry)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 4)
            if onList {
                Image(systemName: "checkmark").foregroundStyle(.secondary).help(L("Already on your list"))
            } else {
                Button {
                    if model.controller.addStation(toStation(entry)) == .duplicate {
                        message = L("This station is already on the list.")
                    }
                } label: {
                    Image(systemName: "plus")
                }
                .buttonStyle(.borderless)
                .help(L("Add to your stations"))
            }
        }
        .padding(.vertical, 2)
    }
}
