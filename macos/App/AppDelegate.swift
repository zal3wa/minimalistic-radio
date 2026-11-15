import AppKit
import RadioCore

/// The radio lives in the menu bar (LSUIElement: no Dock icon, no menus of its own).
@main
final class AppDelegate: NSObject, NSApplicationDelegate {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }

    private var statusItem: NSStatusItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        let image = NSImage(named: "MenuBarIcon")
        image?.isTemplate = true
        image?.size = NSSize(width: 18, height: 18)
        item.button?.image = image
        item.button?.toolTip = "Minimalistic Radio"
        let menu = NSMenu()
        menu.addItem(withTitle: L("Quit"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.menu = menu
        statusItem = item

        if CommandLine.arguments.contains("--self-test") {
            selfTest(item)
        }
    }

    /// `--self-test` (CI): the app starts and builds what it shows; exit code 0 when everything is there.
    private func selfTest(_ item: NSStatusItem) {
        var failures: [String] = []
        if item.button?.image == nil { failures.append("no menu bar icon") }
        let saved = localizer.setting
        localizer.setting = "pl"
        if L("Quit") != "Zakończ" { failures.append("the Polish catalogue didn't load from the app bundle") }
        localizer.setting = saved
        for failure in failures { FileHandle.standardError.write(Data("self-test failed: \(failure)\n".utf8)) }
        exit(failures.isEmpty ? 0 : 1)
    }
}
