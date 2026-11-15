import AppIntents

/// Ready-made shortcuts: they appear in Spotlight and the Shortcuts app without any setup, and Siri runs them in
/// the languages it speaks. Every phrase names the app, as Apple requires.
struct RadioShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: PlayStationIntent(), phrases: [
            "Play \(\.$station) in \(.applicationName)",
        ])
        AppShortcut(intent: PlayIntent(), phrases: [
            "Play \(.applicationName)",
        ])
        AppShortcut(intent: StopIntent(), phrases: [
            "Stop \(.applicationName)",
        ])
        AppShortcut(intent: NextStationIntent(), phrases: [
            "Next station in \(.applicationName)",
        ])
        AppShortcut(intent: PreviousStationIntent(), phrases: [
            "Previous station in \(.applicationName)",
        ])
    }
}
