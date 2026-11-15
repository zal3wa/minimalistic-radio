import AppIntents
import RadioCore

// Actions for Shortcuts, Siri and Spotlight. They run without opening the panel; a station switch shows the
// card, as a media key does.

enum RadioIntentError: Error, CustomLocalizedStringResourceConvertible {
    case noStations
    case notReady

    var localizedStringResource: LocalizedStringResource {
        switch self {
        case .noStations: return "Add a station first."
        case .notReady: return "Minimalistic Radio isn't ready yet. Try again."
        }
    }
}

enum RadioIntents {
    /// The running radio's controller. A Shortcut can start the app, so this waits a moment for it to be ready.
    @MainActor
    static func controller() async throws -> RadioController {
        for _ in 0..<40 {
            if let controller = AppDelegate.shared?.controller { return controller }
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        throw RadioIntentError.notReady
    }

    @MainActor
    static func stations() async throws -> [StationEntity] {
        try await controller().stations.map { StationEntity(id: $0.url, name: $0.name) }
    }

    /// Plays `station` (a stream address), or the last one. Throws when there is nothing to play.
    @MainActor
    static func play(_ station: String?, on c: RadioController) throws {
        if let station, let index = c.stations.firstIndex(where: { $0.url == station }) {
            c.select(index, switched: true)
        }
        if !c.play() { throw RadioIntentError.noStations }
    }
}

struct PlayIntent: AppIntent {
    static var title: LocalizedStringResource = "Play"
    static var description = IntentDescription("Plays the last station.")
    static var openAppWhenRun = false

    @MainActor
    func perform() async throws -> some IntentResult {
        try RadioIntents.play(nil, on: try await RadioIntents.controller())
        return .result()
    }
}

struct PlayStationIntent: AppIntent {
    static var title: LocalizedStringResource = "Play Station"
    static var description = IntentDescription("Plays one of your stations.")
    static var openAppWhenRun = false

    @Parameter(title: "Station")
    var station: StationEntity

    @MainActor
    func perform() async throws -> some IntentResult {
        try RadioIntents.play(station.id, on: try await RadioIntents.controller())
        return .result()
    }
}

struct StopIntent: AppIntent {
    static var title: LocalizedStringResource = "Stop"
    static var description = IntentDescription("Stops the radio.")
    static var openAppWhenRun = false

    @MainActor
    func perform() async throws -> some IntentResult {
        let c = try await RadioIntents.controller()
        if c.active { c.stop() }
        return .result()
    }
}

struct NextStationIntent: AppIntent {
    static var title: LocalizedStringResource = "Next Station"
    static var description = IntentDescription("Switches to the next station on your list.")
    static var openAppWhenRun = false

    @MainActor
    func perform() async throws -> some IntentResult {
        let c = try await RadioIntents.controller()
        guard !c.stations.isEmpty else { throw RadioIntentError.noStations }
        c.nextStation()
        return .result()
    }
}

struct PreviousStationIntent: AppIntent {
    static var title: LocalizedStringResource = "Previous Station"
    static var description = IntentDescription("Switches to the previous station on your list.")
    static var openAppWhenRun = false

    @MainActor
    func perform() async throws -> some IntentResult {
        let c = try await RadioIntents.controller()
        guard !c.stations.isEmpty else { throw RadioIntentError.noStations }
        c.previousStation()
        return .result()
    }
}

struct SleepTimerIntent: AppIntent {
    static var title: LocalizedStringResource = "Set Sleep Timer"
    static var description = IntentDescription("Stops the radio after the minutes you choose. 0 turns the timer off.")
    static var openAppWhenRun = false

    @Parameter(title: "Minutes", default: 30, inclusiveRange: (0, 600))
    var minutes: Int

    @MainActor
    func perform() async throws -> some IntentResult {
        try await RadioIntents.controller().setSleepTimer(minutes: minutes > 0 ? minutes : nil)
        return .result()
    }
}

struct VolumeIntent: AppIntent {
    static var title: LocalizedStringResource = "Set Volume"
    static var description = IntentDescription("Sets the radio's volume, from 0 to 100.")
    static var openAppWhenRun = false

    @Parameter(title: "Volume", default: 50, inclusiveRange: (0, 100))
    var percent: Int

    @MainActor
    func perform() async throws -> some IntentResult {
        try await RadioIntents.controller().setVolume(percent)
        return .result()
    }
}
