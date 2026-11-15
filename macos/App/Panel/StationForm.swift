import RadioCore
import SwiftUI

/// Add a station by its address, or edit one: name, stream address and an optional logo address.
struct StationForm: View {
    @ObservedObject var model: PanelModel
    let index: Int?
    @State private var name = ""
    @State private var address = ""
    @State private var logo = ""
    @State private var problem: String?

    var body: some View {
        Form {
            TextField(L("Station name"), text: $name)
            TextField(L("Stream address (HTTP or HTTPS)"), text: $address)
                .onChange(of: address) { text in
                    // A pasted share link opens its Shared station page (adding a new station only).
                    if index == nil { _ = model.openSharedText(text, complete: false) }
                }
            TextField(L("Logo address (optional)"), text: $logo)
            if let problem {
                Text(problem).foregroundStyle(.red).font(.callout)
            }
            HStack {
                Spacer()
                Button(L("Cancel")) { model.page = .stations }
                    .keyboardShortcut(.cancelAction)
                Button(L("Save")) { save() }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .formStyle(.grouped)
        .onAppear(perform: fill)
    }

    private func fill() {
        guard let index, model.controller.stations.indices.contains(index) else { return }
        let station = model.controller.stations[index]
        name = station.name
        address = station.url
        logo = station.logo ?? ""
    }

    private func save() {
        if index == nil && model.openSharedText(address, complete: true) { return }
        let station = Station(name: name, url: address, logo: logo.isEmpty ? nil : logo)
        let result = index.map { model.controller.updateStation($0, station) } ?? model.controller.addStation(station)
        switch result {
        case .added: model.page = .stations
        case .duplicate: problem = L("This address is already on the list.")
        case .invalid: problem = L("Enter a name and a valid stream address. The logo is optional.")
        }
    }
}
