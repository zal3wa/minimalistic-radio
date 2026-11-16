import AppKit
import RadioCore
import SwiftUI

/// The station card (the Windows card at the bottom of the screen): for a moment under the menu bar icon after a
/// media key, the menu or Shortcuts switched the station, or to say "Copied to clipboard". It shows the station's
/// logo or the cover, the station and the song, follows them while it is up, and lets clicks through.
@MainActor
final class CardController {
    static let size = CGSize(width: 320, height: 72)
    static let seconds: TimeInterval = 3

    private let controller: RadioController
    private let logos: LogoCache
    private let content: CardContent
    private var window: NSPanel?
    private var hide: DispatchWorkItem?

    init(controller: RadioController, logos: LogoCache) {
        self.controller = controller
        self.logos = logos
        content = CardContent(logos: logos)
        controller.subscribe { [weak self] change in
            guard let self, self.window?.isVisible == true, self.content.text == nil,
                  !change.intersection([.track, .cover, .state]).isEmpty else { return }
            self.fill(text: nil)
        }
    }

    /// Shows the card under `anchor` (the icon's frame, nil: top right): the station now, or `text`.
    func show(text: String?, anchor: CGRect?) {
        let window = self.window ?? makeWindow()
        self.window = window
        fill(text: text)
        let screen = NSScreen.screens.first { anchor.map($0.frame.intersects) ?? false } ?? NSScreen.main ?? NSScreen.screens[0]
        window.setFrameOrigin(panelOrigin(anchor: anchor, visibleFrame: screen.visibleFrame, size: Self.size))
        window.orderFrontRegardless()
        hide?.cancel()
        let work = DispatchWorkItem { [weak window] in window?.orderOut(nil) }
        hide = work
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.seconds, execute: work)
    }

    private func fill(text: String?) {
        content.text = text
        content.station = controller.stationName ?? appName
        content.song = text ?? controller.track ?? statusText(controller)
        content.logo = controller.stations.indices.contains(controller.current) ? controller.stations[controller.current].logo : nil
        content.cover = LogoCache.cover(controller.coverPath)
    }

    private func makeWindow() -> NSPanel {
        let window = NSPanel(contentRect: CGRect(origin: .zero, size: Self.size),
                             styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        window.level = .statusBar
        window.backgroundColor = .clear
        window.isOpaque = false
        window.hasShadow = true
        window.ignoresMouseEvents = true
        window.isReleasedWhenClosed = false
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        let background = NSVisualEffectView(frame: CGRect(origin: .zero, size: Self.size))
        background.material = .hudWindow
        background.blendingMode = .behindWindow
        background.state = .active
        background.wantsLayer = true
        background.layer?.cornerRadius = 12
        background.layer?.masksToBounds = true
        let view = NSHostingView(rootView: CardView(content: content))
        view.frame = background.bounds
        view.autoresizingMask = [.width, .height]
        background.addSubview(view)
        window.contentView = background
        return window
    }
}

@MainActor
final class CardContent: ObservableObject {
    let logos: LogoCache
    @Published var text: String?
    @Published var station = ""
    @Published var song = ""
    @Published var logo: String?
    @Published var cover: NSImage?

    init(logos: LogoCache) {
        self.logos = logos
    }
}

struct CardView: View {
    @ObservedObject var content: CardContent

    var body: some View {
        HStack(spacing: 12) {
            Group {
                if content.text != nil {
                    Image(systemName: "checkmark.circle.fill").font(.largeTitle).foregroundStyle(.green)
                } else if let cover = content.cover {
                    Image(nsImage: cover).resizable().aspectRatio(contentMode: .fill)
                } else {
                    LogoView(logos: content.logos, url: content.logo, size: 48)
                }
            }
            .frame(width: 48, height: 48)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            VStack(alignment: .leading, spacing: 2) {
                if content.text == nil {
                    Text(content.station).font(.headline).lineLimit(1)
                }
                Text(content.song).lineLimit(content.text == nil ? 1 : 2).foregroundStyle(content.text == nil ? .secondary : .primary)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .frame(width: CardController.size.width, height: CardController.size.height)
    }
}
