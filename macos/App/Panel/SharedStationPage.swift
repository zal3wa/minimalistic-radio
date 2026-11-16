import AppKit
import RadioCore
import SwiftUI

/// A station from a share link: its logo, name and stream address, the question, [+ Add] and under it "Play
/// automatically" (checked the first time, then the choice saved with the last Add). Nothing is added without Add,
/// and nothing plays unless the box is checked; Cancel, ‹ and Esc change nothing (the choice isn't saved). A link
/// without a station only says so.
struct SharedStationPage: View {
    @ObservedObject var model: PanelModel
    let station: SharedStation?
    @State private var play: Bool

    init(model: PanelModel, station: SharedStation?) {
        self.model = model
        self.station = station
        _play = State(initialValue: model.controller.prefs.playSharedStations)
    }

    var body: some View {
        if let station {
            VStack(spacing: 0) {
                VStack(spacing: 0) {
                    LogoView(logos: model.logos, url: station.logo, size: 72, corner: 14)
                    Text(station.name)
                        .font(.system(size: 17, weight: .bold))
                        .multilineTextAlignment(.center)
                        .padding(.top, 14)
                    Text(shownAddress(station.url))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .lineLimit(3)
                        .padding(.top, 4)
                    Text(L("Add it to your stations?"))
                        .multilineTextAlignment(.center)
                        .padding(.top, 14)
                    Button { model.addShared(station, play: play) } label: {
                        Label(L("Add"), systemImage: "plus").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
                    .padding(.top, 18)
                    // The Mac's own checkbox, centred under Add (Space toggles it when it has the focus).
                    Toggle(L("Play automatically"), isOn: $play)
                        .toggleStyle(.checkbox)
                        .padding(.top, 10)
                    Button { model.back() } label: {
                        Text(L("Cancel")).frame(maxWidth: .infinity)
                    }
                    .controlSize(.large)
                    .padding(.top, 12)
                }
                .padding(EdgeInsets(top: 28, leading: 20, bottom: 20, trailing: 20))
                .frame(maxWidth: .infinity)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color.primary.opacity(0.06)))
                Spacer(minLength: 0)
            }
            .padding(12)
        } else {
            Text(L("This link doesn't contain a station."))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(24)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    /// The address as people read it: without http(s)://.
    private func shownAddress(_ url: String) -> String {
        for scheme in ["https://", "http://"] where url.lowercased().hasPrefix(scheme) {
            return String(url.dropFirst(scheme.count))
        }
        return url
    }
}
