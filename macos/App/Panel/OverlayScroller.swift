import AppKit
import SwiftUI

/// Put in a list's row: keeps that list's scroll bar over the content, as with a trackpad, even where the Mac shows
/// scroll bars all the time (a mouse). Otherwise a long list leaves a scroll bar's width empty on the right, and its
/// rows end further from the right edge (about 33 pt) than from the left one (16 pt).
struct OverlayScroller: NSViewRepresentable {
    func makeNSView(context: Context) -> Probe {
        Probe()
    }

    func updateNSView(_ probe: Probe, context: Context) {
        probe.apply()
    }

    final class Probe: NSView {
        private var observer: NSObjectProtocol?

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            apply()
            guard observer == nil, window != nil else { return }
            // The scroll view goes back to the system's style when that setting changes: set it again after it.
            observer = NotificationCenter.default.addObserver(forName: NSScroller.preferredScrollerStyleDidChangeNotification,
                                                              object: nil, queue: .main) { [weak self] _ in
                DispatchQueue.main.async { self?.apply() }
            }
        }

        func apply() {
            guard let scroll = enclosingScrollView, scroll.scrollerStyle != .overlay else { return }
            scroll.scrollerStyle = .overlay
        }

        deinit {
            if let observer { NotificationCenter.default.removeObserver(observer) }
        }
    }
}
