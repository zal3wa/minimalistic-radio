import AppKit
import RadioCore
import SwiftUI

/// A borderless panel that can take the keyboard (for the search box): Esc goes back a page or closes it.
final class KeyPanel: NSPanel {
    var onCancel: () -> Void = {}
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
    override func cancelOperation(_ sender: Any?) { onCancel() }
}

/// The panel the menu bar icon opens (the Windows left click): just under the icon, in the system's material,
/// closed by a click elsewhere, Esc or another click on the icon.
@MainActor
final class PanelController: NSObject, NSWindowDelegate {
    static let size = CGSize(width: 412, height: 602)

    let model: PanelModel
    private var panel: KeyPanel?
    private var closedAt = Date.distantPast
    /// While a file dialog or an alert of the panel's is open, losing the focus doesn't close the panel.
    var keepOpen = false

    init(model: PanelModel) {
        self.model = model
        super.init()
        model.close = { [weak self] in self?.close() }
    }

    var isVisible: Bool { panel?.isVisible == true }

    /// Opens the panel on `page` (or the stations), under `anchor` (the icon's frame) or at the top right.
    func show(page: PanelModel.Page? = nil, anchor: CGRect?) {
        let panel = self.panel ?? makePanel()
        self.panel = panel
        if !isVisible { model.suggested = nil }
        model.page = page ?? (isVisible ? model.page : .stations)
        let screen = NSScreen.screens.first { anchor.map($0.frame.intersects) ?? false } ?? NSScreen.main ?? NSScreen.screens[0]
        panel.setFrameOrigin(panelOrigin(anchor: anchor, visibleFrame: screen.visibleFrame, size: Self.size))
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
    }

    /// The icon was clicked: opens the panel, or closes it if it is open (or was closed by this very click).
    func toggle(anchor: CGRect?) {
        if isVisible {
            close()
        } else if Date().timeIntervalSince(closedAt) > 0.3 {
            show(anchor: anchor)
        }
    }

    func close() {
        guard let panel, panel.isVisible else { return }
        closedAt = Date()
        panel.orderOut(nil)
    }

    private func makePanel() -> KeyPanel {
        let panel = KeyPanel(contentRect: CGRect(origin: .zero, size: Self.size),
                             styleMask: [.borderless, .fullSizeContentView], backing: .buffered, defer: false)
        panel.isFloatingPanel = true
        panel.level = .statusBar
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.delegate = self
        panel.onCancel = { [weak self] in self?.model.back() }

        let background = NSVisualEffectView(frame: CGRect(origin: .zero, size: Self.size))
        background.material = .popover
        background.blendingMode = .behindWindow
        background.state = .active
        background.wantsLayer = true
        background.layer?.cornerRadius = 12
        background.layer?.masksToBounds = true
        let content = NSHostingView(rootView: PanelView(model: model))
        content.frame = background.bounds
        content.autoresizingMask = [.width, .height]
        background.addSubview(content)
        panel.contentView = background
        return panel
    }

    /// A click elsewhere closes the panel, unless the focus went to one of the panel's own dialogs.
    func windowDidResignKey(_ notification: Notification) {
        DispatchQueue.main.async { [weak self] in
            guard let self, !self.keepOpen, let panel = self.panel else { return }
            if let key = NSApp.keyWindow, key == panel || key.sheetParent == panel { return }
            self.close()
        }
    }
}
