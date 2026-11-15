import RadioCore
import SwiftUI

/// The station list: logo, name, the playing mark and a ⋯ menu. A click plays a station; dragging reorders the
/// list (the Mac list's own drag), and ⌘⌥↑/↓ move the selected station.
struct StationsPage: View {
    @ObservedObject var model: PanelModel
    @State private var selected: String?

    private var controller: RadioController { model.controller }

    var body: some View {
        if controller.stations.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "dot.radiowaves.left.and.right").font(.largeTitle).foregroundStyle(.secondary)
                Button(L("Add a station")) { model.page = .search }
                    .buttonStyle(.borderedProminent)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(selection: $selected) {
                ForEach(Array(controller.stations.enumerated()), id: \.element.url) { index, station in
                    StationRow(model: model, station: station, index: index) { play(index) }
                        .tag(station.url)
                        .background(OverlayScroller())
                }
                .onMove { from, to in
                    if let source = from.first { controller.moveStation(from: source, to: to) }
                }
            }
            .listStyle(.inset)
            .scrollContentBackground(.hidden)
            .background(alignment: .bottom) {
                // ⌘⌥↑/↓: the keyboard way to move the selected station.
                HStack {
                    Button("") { move(-1) }.keyboardShortcut(.upArrow, modifiers: [.command, .option])
                    Button("") { move(1) }.keyboardShortcut(.downArrow, modifiers: [.command, .option])
                }
                .opacity(0)
            }
        }
    }

    private func play(_ index: Int) {
        selected = controller.stations[index].url
        controller.select(index)
        controller.play()
    }

    private func move(_ delta: Int) {
        guard let selected, let index = controller.stations.firstIndex(where: { $0.url == selected }) else { return }
        let target = index + delta
        guard controller.stations.indices.contains(target) else { return }
        controller.moveStation(from: index, to: delta > 0 ? target + 1 : target)
    }
}

struct StationRow: View {
    @ObservedObject var model: PanelModel
    let station: Station
    let index: Int
    let onPlay: () -> Void

    private var playing: Bool { model.controller.current == index && model.controller.active }

    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: 12) {
                LogoView(logos: model.logos, url: station.logo, size: 40)
                Text(station.name)
                    .lineLimit(1)
                    .foregroundStyle(playing ? Color.accentColor : Color.primary)
                Spacer(minLength: 4)
                if playing {
                    Image(systemName: "play.fill").foregroundStyle(Color.accentColor)
                }
            }
            .contentShape(Rectangle())
            .onTapGesture(perform: onPlay)
            Menu {
                Button(L("Edit")) { model.page = .station(index) }
                Button(L("Remove"), role: .destructive) { model.controller.removeStation(index) }
            } label: {
                Image(systemName: "ellipsis")
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help(L("Station options"))
        }
        .padding(.vertical, 4)
    }
}

/// A station's logo from the cache, a symbol until it arrives (or if there is none). Keyed by the address, so a
/// redrawn or reordered list keeps its pictures.
struct LogoView: View {
    let logos: LogoCache
    let url: String?
    let size: CGFloat
    @State private var image: NSImage?

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image).resizable().interpolation(.high).aspectRatio(contentMode: .fit)
            } else {
                Image(systemName: "dot.radiowaves.left.and.right").foregroundStyle(.secondary)
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .task(id: url) {
            let known = logos.lookup(url)
            image = known.image
            if !known.known, let url {
                logos.load(url) { image = $0 }
            }
        }
    }
}
