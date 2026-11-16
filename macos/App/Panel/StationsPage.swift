import RadioCore
import SwiftUI
import UniformTypeIdentifiers

/// The station list: logo, name, the playing mark and a ⋯ menu. A click plays a station; dragging a station reorders the
/// list (StationDrop), and ⌘⌥↑/↓ move the selected station. After a shared station it shows that one.
struct StationsPage: View {
    @ObservedObject var model: PanelModel
    @State private var selected: String?
    /// The address of the station being dragged, while a drag lasts.
    @State private var dragging: String?

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
            ScrollViewReader { proxy in
                List(selection: $selected) {
                    ForEach(Array(controller.stations.enumerated()), id: \.element.url) { index, station in
                        StationRow(model: model, station: station, index: index) { play(index) }
                            .tag(station.url)
                            // The row's click (play) takes the mouse, so the list's own drag (onMove) never starts
                            // on a Mac: the row is a drag source of its own, and the list follows it as it moves.
                            .onDrag {
                                dragging = station.url
                                return NSItemProvider(object: station.url as NSString)
                            }
                            .onDrop(of: [.text], delegate: StationDrop(target: station.url, controller: controller,
                                                                       dragging: $dragging))
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
                .onAppear { scrollToTarget(proxy) }
                .onChange(of: model.scrollTarget) { _ in scrollToTarget(proxy) }
            }
        }
    }

    /// A shared station, just added or already on the list: scrolled into view once the list is laid out.
    private func scrollToTarget(_ proxy: ScrollViewProxy) {
        guard let target = model.scrollTarget else { return }
        DispatchQueue.main.async {
            proxy.scrollTo(target)
            model.scrollTarget = nil
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

/// Dragging a station over another one moves it there at once (the list reorders under the pointer); dropping ends
/// the drag. Only a drag that started on this list moves anything.
struct StationDrop: DropDelegate {
    let target: String
    let controller: RadioController
    @Binding var dragging: String?

    func dropEntered(info: DropInfo) {
        guard let dragging, dragging != target,
              let from = controller.stations.firstIndex(where: { $0.url == dragging }),
              let to = controller.stations.firstIndex(where: { $0.url == target }) else { return }
        controller.moveStation(from: from, to: to > from ? to + 1 : to)
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: dragging == nil ? .forbidden : .move)
    }

    func validateDrop(info: DropInfo) -> Bool { dragging != nil }

    func performDrop(info: DropInfo) -> Bool {
        dragging = nil
        return true
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
                Button(L("Share")) { model.share(station) }
                Divider()
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
    var corner: CGFloat = 6
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
        .clipShape(RoundedRectangle(cornerRadius: corner))
        .task(id: url) {
            let known = logos.lookup(url)
            image = known.image
            if !known.known, let url {
                logos.load(url) { image = $0 }
            }
        }
    }
}
