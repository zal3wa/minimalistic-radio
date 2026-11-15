import AppKit
import RadioCore

/// The radio's icon in the menu bar. A click opens the panel (the Windows left click); a right click or a
/// Control-click opens the menu (the Windows right click).
@MainActor
final class StatusItemController: NSObject {
    private let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let controller: RadioController
    private let onClick: () -> Void
    private let perform: (String) -> Void
    /// The label of a ready update for the menu ("Update"), nil when there is none.
    var updateLabel: () -> String? = { nil }
    /// Items added below the menu (the risk-check beta's Import and Open at login; Task 17 removes them).
    var extraItems: () -> [NSMenuItem] = { [] }

    init(controller: RadioController, onClick: @escaping () -> Void, perform: @escaping (String) -> Void) {
        self.controller = controller
        self.onClick = onClick
        self.perform = perform
        super.init()
        let image = NSImage(named: "MenuBarIcon")
        image?.isTemplate = true
        image?.size = NSSize(width: 18, height: 18)
        item.button?.image = image
        item.button?.setAccessibilityLabel(appName)
        item.button?.target = self
        item.button?.action = #selector(clicked(_:))
        item.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])
        refresh()
    }

    var hasIcon: Bool { item.button?.image != nil }

    /// The icon's frame on the screen, nil when it isn't shown (hidden behind a MacBook's notch, for example).
    var buttonFrameOnScreen: CGRect? {
        guard let button = item.button, let window = button.window, window.occlusionState.contains(.visible) else { return nil }
        return window.convertToScreen(button.convert(button.bounds, to: nil))
    }

    func refresh() {
        item.button?.toolTip = tooltip(controller)
    }

    @objc private func clicked(_ sender: NSStatusBarButton) {
        let event = NSApp.currentEvent
        if event?.type == .rightMouseUp || event?.modifierFlags.contains(.control) == true {
            showMenu()
        } else {
            onClick()
        }
    }

    func makeMenu() -> NSMenu {
        let menu = MenuBuilder.make(buildMenu(controller, update: updateLabel(), localize: L), perform: perform)
        let extras = extraItems()
        if !extras.isEmpty {
            menu.addItem(.separator())
            extras.forEach(menu.addItem)
        }
        return menu
    }

    func showMenu() {
        item.menu = makeMenu()
        item.button?.performClick(nil)
        item.menu = nil
    }
}

/// NSMenu from the menu model; each item calls `perform` with its id.
enum MenuBuilder {
    final class Action: NSObject {
        let run: () -> Void
        init(_ run: @escaping () -> Void) { self.run = run }
        @objc func fire(_ sender: Any?) { run() }
    }

    static func make(_ items: [MenuItem], perform: @escaping (String) -> Void) -> NSMenu {
        let menu = NSMenu()
        menu.autoenablesItems = false
        for model in items {
            if model.separator {
                menu.addItem(.separator())
                continue
            }
            let entry = NSMenuItem(title: model.label, action: nil, keyEquivalent: "")
            entry.isEnabled = model.enabled
            entry.state = model.checked ? .on : .off
            if let symbol = model.symbol {
                entry.image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)
            }
            if model.children.isEmpty {
                let action = Action { perform(model.id) }
                entry.target = action
                entry.action = #selector(Action.fire(_:))
                entry.representedObject = action   // keeps the action alive as long as the item
            } else {
                entry.submenu = make(model.children, perform: perform)
            }
            menu.addItem(entry)
        }
        return menu
    }

    /// A menu item that runs `run` (for items outside the model).
    static func item(_ title: String, checked: Bool = false, run: @escaping () -> Void) -> NSMenuItem {
        let action = Action(run)
        let entry = NSMenuItem(title: title, action: #selector(Action.fire(_:)), keyEquivalent: "")
        entry.target = action
        entry.representedObject = action
        entry.state = checked ? .on : .off
        return entry
    }
}
