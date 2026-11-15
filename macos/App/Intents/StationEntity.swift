import AppIntents
import RadioCore

/// One of the user's stations, for Shortcuts and Siri: Play Antyradio Hard in Minimalistic Radio.
/// The id is the stream address, as in stations.json.
struct StationEntity: AppEntity {
    static var typeDisplayRepresentation: TypeDisplayRepresentation = "Station"
    static var defaultQuery = StationQuery()

    let id: String
    let name: String

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)")
    }
}

struct StationQuery: EntityStringQuery {
    func entities(for identifiers: [String]) async throws -> [StationEntity] {
        try await RadioIntents.stations().filter { identifiers.contains($0.id) }
    }

    func entities(matching string: String) async throws -> [StationEntity] {
        try await RadioIntents.stations().filter { $0.name.localizedCaseInsensitiveContains(string) }
    }

    func suggestedEntities() async throws -> [StationEntity] {
        try await RadioIntents.stations()
    }
}
