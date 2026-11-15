import AppKit
import RadioCore
import SwiftUI

/// Song history: the song, "station · time", and a ⋯ menu to copy it or look it up on Spotify or YouTube.
struct HistoryPage: View {
    @ObservedObject var model: PanelModel

    private var history: [HistoryEntry] { model.controller.history }

    var body: some View {
        if history.isEmpty {
            Text(L("Songs the radio plays will show up here."))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            VStack(alignment: .leading, spacing: 4) {
                List {
                    ForEach(Array(history.enumerated()), id: \.offset) { _, entry in
                        HistoryRow(entry: entry)
                    }
                }
                .listStyle(.inset)
                .scrollContentBackground(.hidden)
                Button(L("Clear history")) { model.controller.clearHistory() }
                    .buttonStyle(.link)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 4)
            }
        }
    }
}

struct HistoryRow: View {
    let entry: HistoryEntry

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.title).lineLimit(2)
                Text("\(entry.station) · \(time)").font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 4)
            Menu {
                Button(L("Copy")) {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(entry.title, forType: .string)
                }
                Button(L("Search on Spotify")) { open("https://open.spotify.com/search/") }
                Button(L("Search on YouTube")) { open("https://www.youtube.com/results?search_query=") }
            } label: {
                Image(systemName: "ellipsis")
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help(L("More"))
        }
        .padding(.vertical, 2)
    }

    /// The time in the UI's language (24 h where that is the custom).
    private var time: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: localizer.language)
        formatter.timeStyle = .short
        formatter.dateStyle = Calendar.current.isDateInToday(entry.time) ? .none : .short
        return formatter.string(from: entry.time)
    }

    /// The song as search words: the artist separator dropped, everything percent-encoded (as Linux does).
    private func open(_ base: String) {
        let words = entry.title.replacingOccurrences(of: " – ", with: " ").replacingOccurrences(of: " - ", with: " ")
        let unreserved = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        if let url = URL(string: base + (words.addingPercentEncoding(withAllowedCharacters: unreserved) ?? "")) {
            NSWorkspace.shared.open(url)
        }
    }
}
