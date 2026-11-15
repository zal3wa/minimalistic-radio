import AppKit
import RadioCore
import SwiftUI

/// A station from a share link: its logo, name and stream address, and the question. Nothing is added or played
/// without Add and play; Cancel, ‹ and Esc change nothing. A link without a station only says so.
struct SharedStationPage: View {
    @ObservedObject var model: PanelModel
    let station: SharedStation?

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
                    Text(L("Add it to your stations and play it now?"))
                        .multilineTextAlignment(.center)
                        .padding(.top, 14)
                    Button { model.addShared(station) } label: {
                        Label(L("Add and play"), systemImage: "play.fill").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
                    .padding(.top, 18)
                    Button { model.back() } label: {
                        Text(L("Cancel")).frame(maxWidth: .infinity)
                    }
                    .controlSize(.large)
                    .padding(.top, 8)
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
