import AVKit
import RadioCore
import SwiftUI

/// The bottom of the panel, as on Windows: what plays now, the volume row and Play/Stop.
struct FooterView: View {
    @ObservedObject var model: PanelModel

    var body: some View {
        VStack(spacing: 10) {
            NowPlayingCard(model: model)
            VolumeRow(model: model)
            PlayStopButton(model: model)
        }
        .padding(12)
    }
}

/// "Now playing": the cover (or the station's logo), the song or the radio's state, and a copy button that turns
/// into a check mark with "Copied" for a moment.
struct NowPlayingCard: View {
    @ObservedObject var model: PanelModel
    @State private var cover: NSImage?
    @State private var copied = false

    private var controller: RadioController { model.controller }

    var body: some View {
        HStack(spacing: 12) {
            Group {
                if let cover {
                    Image(nsImage: cover).resizable().aspectRatio(contentMode: .fill)
                } else if controller.stations.indices.contains(controller.current) {
                    LogoView(logos: model.logos, url: controller.stations[controller.current].logo, size: 48)
                } else {
                    Image(systemName: "music.note").foregroundStyle(.secondary)
                }
            }
            .frame(width: 48, height: 48)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            VStack(alignment: .leading, spacing: 2) {
                Text(L("Now playing")).font(.caption).foregroundStyle(.secondary)
                Text(controller.track ?? statusText(controller))
                    .lineLimit(2)
                    .font(.body.weight(controller.track == nil ? .regular : .medium))
            }
            Spacer(minLength: 4)
            Button(action: copy) {
                if copied {
                    Label(L("Copied"), systemImage: "checkmark").labelStyle(.titleAndIcon)
                } else {
                    Image(systemName: "doc.on.doc")
                }
            }
            .buttonStyle(.borderless)
            .disabled(controller.track == nil)
            .help(L("Copy title"))
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.primary.opacity(0.06)))
        .task(id: controller.coverPath) {
            cover = controller.coverPath.flatMap { NSImage(contentsOf: $0) }
        }
    }

    private func copy() {
        guard let track = controller.track else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(track, forType: .string)
        copied = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { copied = false }
    }
}

/// The radio's state in words, when there is no song to show.
@MainActor
func statusText(_ c: RadioController) -> String {
    if let message = c.message { return message }
    switch c.status {
    case .ready: return c.stations.isEmpty ? L("Add a station") : L("Ready to play")
    case .connecting: return L("Connecting to the station…")
    case .playing: return L("The station doesn't send song titles")
    case .retrying: return L("Connecting to the station…")
    case .stopped: return L("Stopped")
    }
}

/// The volume, as on Windows 11: a speaker that mutes, a slider whose value shows while it is dragged, the sleep
/// timer behind the moon, and the AirPlay button.
struct VolumeRow: View {
    @ObservedObject var model: PanelModel
    @State private var dragging = false

    private var controller: RadioController { model.controller }

    private var speaker: String {
        switch controller.volume {
        case 0: return "speaker.slash.fill"
        case 1..<34: return "speaker.wave.1.fill"
        case 34..<67: return "speaker.wave.2.fill"
        default: return "speaker.wave.3.fill"
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            Button { controller.toggleMute() } label: {
                Image(systemName: speaker).frame(width: 22)
            }
            .buttonStyle(.borderless)
            .help(controller.volume == 0 ? L("Unmute") : L("Mute"))

            Slider(value: Binding(get: { Double(controller.volume) },
                                  set: { controller.setVolume(Int($0.rounded())) }),
                   in: 0...100) { editing in dragging = editing }
                .overlay(alignment: .topLeading) {
                    GeometryReader { geometry in
                        if dragging {
                            Text("\(controller.volume)")
                                .font(.caption.monospacedDigit())
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.regularMaterial, in: Capsule())
                                .position(x: 10 + (geometry.size.width - 20) * CGFloat(controller.volume) / 100, y: -14)
                        }
                    }
                }
                .help(L("Volume"))

            Menu {
                ForEach(sleepChoices, id: \.id) { choice in
                    Button {
                        controller.setSleepTimer(minutes: choice.id == "sleep:off" ? nil : Int(choice.id.dropFirst(6)))
                    } label: {
                        if choice.checked { Label(choice.label, systemImage: "checkmark") } else { Text(choice.label) }
                    }
                }
            } label: {
                Image(systemName: controller.sleepAt == nil ? "moon" : "moon.fill")
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help(sleepLabel)

            AirPlayButton()
                .frame(width: 22, height: 22)
                .help("AirPlay")
        }
        .imageScale(.large)
    }

    private var sleepMenu: MenuItem? {
        buildMenu(controller, update: nil, localize: L).first { $0.id == "sleep" }
    }

    private var sleepChoices: [MenuItem] { sleepMenu?.children ?? [] }
    private var sleepLabel: String { sleepMenu?.label ?? L("Sleep timer") }
}

/// AirPlay: plays the radio on HomePods, Apple TVs and AirPlay speakers.
struct AirPlayButton: NSViewRepresentable {
    func makeNSView(context: Context) -> AVRoutePickerView {
        let picker = AVRoutePickerView()
        picker.player = AppDelegate.shared?.player?.avPlayer
        picker.isRoutePickerButtonBordered = false
        return picker
    }

    func updateNSView(_ picker: AVRoutePickerView, context: Context) {
        picker.player = AppDelegate.shared?.player?.avPlayer
    }
}

/// Play or Stop, as wide as the panel.
struct PlayStopButton: View {
    @ObservedObject var model: PanelModel

    var body: some View {
        let active = model.controller.active
        Button { model.controller.toggle() } label: {
            Label(active ? L("Stop") : L("Play"), systemImage: active ? "stop.fill" : "play.fill")
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(model.controller.stations.isEmpty)
        .keyboardShortcut(.space, modifiers: [])
    }
}
