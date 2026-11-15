import Foundation
import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_menu_model.py; the MPRIS cases become Now Playing cases.

@MainActor private func playingRig() -> Rig {
    var prefs = Preferences()
    prefs.volume = 30
    let r = Rig.started(stations: [Station(name: "Radio A", url: "http://a.example/live"),
                                   Station(name: "Radio B", url: "http://b.example/live")], prefs: prefs)
    playing(r.controller)
    r.controller.track = "Leonard Cohen - Everybody Knows"
    return r
}

private func item(_ items: [MenuItem], _ id: String) -> MenuItem? {
    items.first { $0.id == id }
}

private func hhmm(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "HH:mm"
    return formatter.string(from: date)
}

@MainActor @Test func menuOrderAndLabels() {
    let c = playingRig().controller
    let menu = buildMenu(c, update: nil)
    #expect(menu.map(\.id) == ["playback", "stations", "volume", "sleep", "sep:1", "now:station", "now:track", "sep:2", "settings", "quit"])
    #expect(item(menu, "playback")?.label == "Stop" && item(menu, "volume")?.label == "Volume (30%)")
    #expect(item(menu, "now:station")?.enabled == false && item(menu, "now:track")?.label == "Leonard Cohen - Everybody Knows")
    #expect(item(menu, "stations")?.children.map(\.checked) == [true, false] && item(menu, "stations")?.children.first?.radio == true)
}

@MainActor @Test func volumeBounds() {
    let c = Rig.started().controller
    c.setVolume(100)
    let children = item(buildMenu(c, update: nil), "volume")?.children ?? []
    #expect(children.map(\.id) == ["volume:up", "volume:down", "sep:volume", "volume:0", "volume:25", "volume:50", "volume:75", "volume:100"])
    #expect(item(children, "volume:up")?.enabled == false && item(children, "volume:down")?.enabled == true)
    #expect(item(children, "volume:0")?.label == "Mute")
}

@MainActor @Test func playDisabledWithoutStations() {
    let c = Rig.started(stations: []).controller
    #expect(item(buildMenu(c, update: nil), "playback")?.enabled == false)
}

@MainActor @Test func sleepLabelAndChecks() {
    let c = Rig.started().controller
    c.setSleepTimer(minutes: 30)
    let sleep = item(buildMenu(c, update: nil), "sleep")
    #expect(sleep?.label == "Stops at " + hhmm(c.sleepAt!))
    #expect(item(sleep?.children ?? [], "sleep:30")?.checked == true && item(sleep?.children ?? [], "sleep:off")?.checked == false)
    #expect(item(sleep?.children ?? [], "sleep:15")?.label == "15 min")
}

@MainActor @Test func updateItemOnlyWhenReady() {
    let c = Rig.started().controller
    #expect(item(buildMenu(c, update: "Update"), "update")?.label == "Update")
    #expect(!buildMenu(c, update: nil).contains { $0.id == "update" })
}

@MainActor @Test func noNowItemsWithoutStation() {
    let c = Rig.started().controller
    #expect(buildMenu(c, update: nil).map(\.id) == ["playback", "stations", "volume", "sleep", "sep:1", "sep:2", "settings", "quit"])
}

@MainActor @Test func tooltipTruncated() {
    let c = playingRig().controller
    c.track = String(repeating: "X", count: 400)
    let lines = tooltip(c).components(separatedBy: "\n")
    #expect(lines.first == "Minimalistic Radio · Radio A")
    #expect(lines.count == 2 && lines[1].count <= 120 && lines[1].hasSuffix("…"))
}

@MainActor @Test func trackItemTruncated() {
    let c = playingRig().controller
    c.track = String(repeating: "X", count: 400)
    let label = item(buildMenu(c, update: nil), "now:track")?.label ?? ""
    #expect(label.count <= 120 && label.hasSuffix("…"))
}

@MainActor @Test func nowPlayingShowsTheSongAndTheStation() {
    let c = playingRig().controller
    let info = nowPlayingInfo(c)
    #expect(info.title == "Leonard Cohen - Everybody Knows" && info.artist == "Radio A" && info.artwork == nil)
}

@MainActor @Test func nowPlayingStationOnly() {
    let c = Rig.started().controller
    c.select(0)
    let info = nowPlayingInfo(c)
    #expect(info.title == "Alpha" && info.artist == nil)
}
