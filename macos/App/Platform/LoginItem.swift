import AppKit
import ServiceManagement

/// "Open at login": the radio in System Settings → General → Login Items (SMAppService, macOS 13+).
/// Started that way, it waits in the menu bar and doesn't play by itself, as on Windows.
enum LoginItem {
    static var isEnabled: Bool {
        SMAppService.mainApp.status == .enabled
    }

    /// The user has to allow it in System Settings first.
    static var needsApproval: Bool {
        SMAppService.mainApp.status == .requiresApproval
    }

    static func set(_ on: Bool) throws {
        if on {
            try SMAppService.mainApp.register()
        } else {
            try SMAppService.mainApp.unregister()
        }
    }

    static func openSettings() {
        SMAppService.openSystemSettingsLoginItems()
    }

    /// This launch came from the login items, not from the user: read in applicationDidFinishLaunching.
    @MainActor
    static var launchedAtLogin: Bool {
        guard let event = NSAppleEventManager.shared().currentAppleEvent, event.eventID == kAEOpenApplication else { return false }
        return event.paramDescriptor(forKeyword: keyAEPropData)?.enumCodeValue == keyAELaunchedAsLogInItem
    }
}
