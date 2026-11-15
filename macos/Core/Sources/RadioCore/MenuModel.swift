import Foundation

// The menu bar menu, the tooltip and Now Playing as plain data, so they are tested without AppKit.
// A port of linux/minimalistic_radio/platform/menu_model.py (the Windows tray menu).

let tooltipBodyMax = 120
public let sleepMinutesChoices = [15, 30, 45, 60, 90]
let volumePresets = [0, 25, 50, 75, 100]

public struct MenuItem: Equatable, Sendable {
    public var id: String
    public var label = ""
    public var enabled = true
    public var separator = false
    /// A choice among its siblings, shown with `checked`.
    public var radio = false
    public var checked = false
    /// An SF Symbol name.
    public var symbol: String?
    public var children: [MenuItem] = []

    public init(id: String, label: String = "", enabled: Bool = true, separator: Bool = false, radio: Bool = false,
                checked: Bool = false, symbol: String? = nil, children: [MenuItem] = []) {
        self.id = id
        self.label = label
        self.enabled = enabled
        self.separator = separator
        self.radio = radio
        self.checked = checked
        self.symbol = symbol
        self.children = children
    }
}

private func separatorItem(_ name: String) -> MenuItem {
    MenuItem(id: "sep:\(name)", separator: true)
}

/// At most 120 characters, ending with "…" when cut (a song or a station name can be very long).
func shorten(_ text: String) -> String {
    text.count <= tooltipBodyMax ? text : String(text.prefix(tooltipBodyMax - 1)) + "…"
}

/// "HH:mm", as the Windows and Linux menus show the sleep timer's end.
func clockTime(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "HH:mm"
    return formatter.string(from: date)
}

/// The same menu as the Windows tray; `update` is the label of the ready update, if any.
@MainActor
public func buildMenu(_ c: RadioController, update: String?, localize L: (String) -> String = { $0 }) -> [MenuItem] {
    let volume = c.volume
    var items = [
        MenuItem(id: "playback", label: c.active ? L("Stop") : L("Play"), enabled: c.active || !c.stations.isEmpty,
                 symbol: c.active ? "stop.fill" : "play.fill"),
        MenuItem(id: "stations", label: L("Station"), symbol: "dot.radiowaves.left.and.right",
                 children: c.stations.enumerated().map { index, station in
                     MenuItem(id: "station:\(index)", label: station.name, radio: true, checked: index == c.current)
                 }),
    ]

    var levels = [
        MenuItem(id: "volume:up", label: L("Up 5%"), enabled: volume < 100, symbol: "plus"),
        MenuItem(id: "volume:down", label: L("Down 5%"), enabled: volume > 0, symbol: "minus"),
        separatorItem("volume"),
    ]
    levels += volumePresets.map { preset in
        MenuItem(id: "volume:\(preset)", label: preset == 0 ? L("Mute") : "\(preset)%", radio: true, checked: volume == preset)
    }
    items.append(MenuItem(id: "volume", label: L("Volume") + " (\(volume)%)", symbol: "speaker.wave.2", children: levels))

    let label = c.sleepAt.map { L("Stops at {0}").replacingOccurrences(of: "{0}", with: clockTime($0)) } ?? L("Sleep timer")
    var timer = sleepMinutesChoices.map { minutes in
        MenuItem(id: "sleep:\(minutes)", label: L("{0} min").replacingOccurrences(of: "{0}", with: String(minutes)),
                 radio: true, checked: c.sleepMinutes == minutes)
    }
    timer.append(MenuItem(id: "sleep:off", label: L("Off"), radio: true, checked: c.sleepAt == nil))
    items.append(MenuItem(id: "sleep", label: label, symbol: "moon", children: timer))

    items.append(separatorItem("1"))
    if let name = c.stationName {
        items.append(MenuItem(id: "now:station", label: name, enabled: false))
        if let track = c.track, !track.isEmpty {
            items.append(MenuItem(id: "now:track", label: shorten(track)))   // a click copies it, like Windows
        }
    }
    items.append(separatorItem("2"))
    if let update {
        items.append(MenuItem(id: "update", label: update, symbol: "arrow.down.circle"))
    }
    items.append(MenuItem(id: "settings", label: L("Settings"), symbol: "gearshape"))
    items.append(MenuItem(id: "quit", label: L("Quit"), symbol: "xmark"))
    return items
}

/// "Minimalistic Radio · station", and the song on a second line.
@MainActor
public func tooltip(_ c: RadioController) -> String {
    let title = shorten(c.stationName.map { "\(appName) · \($0)" } ?? appName)
    guard let track = c.track, !track.isEmpty else { return title }
    return title + "\n" + shorten(track)
}

public struct NowPlayingInfo: Equatable, Sendable {
    public let title: String
    public let artist: String?
    public let artwork: URL?
}

/// Control Center's Now Playing: the song as the title and the station as the artist (or the station alone).
@MainActor
public func nowPlayingInfo(_ c: RadioController) -> NowPlayingInfo {
    if let track = c.track, !track.isEmpty {
        return NowPlayingInfo(title: track, artist: c.stationName, artwork: c.coverPath)
    }
    return NowPlayingInfo(title: c.stationName ?? appName, artist: nil, artwork: c.coverPath)
}
