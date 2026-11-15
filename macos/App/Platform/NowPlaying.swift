import AppKit
import MediaPlayer
import RadioCore

/// Control Center's Now Playing, the media keys, AirPods and the Touch Bar (the Windows media controls).
/// Next and Previous switch stations.
@MainActor
final class NowPlaying {
    private let controller: RadioController
    private var coverShown: URL?
    private var artwork: MPMediaItemArtwork?

    init(controller: RadioController) {
        self.controller = controller
        let commands = MPRemoteCommandCenter.shared()
        commands.playCommand.addTarget { [weak self] _ in self?.run { $0.play() } ?? .commandFailed }
        commands.pauseCommand.addTarget { [weak self] _ in self?.run { $0.stop() } ?? .commandFailed }
        commands.stopCommand.addTarget { [weak self] _ in self?.run { $0.stop() } ?? .commandFailed }
        commands.togglePlayPauseCommand.addTarget { [weak self] _ in self?.run { $0.toggle() } ?? .commandFailed }
        commands.nextTrackCommand.addTarget { [weak self] _ in self?.run { $0.nextStation() } ?? .commandFailed }
        commands.previousTrackCommand.addTarget { [weak self] _ in self?.run { $0.previousStation() } ?? .commandFailed }
        update()
    }

    private func run(_ action: (RadioController) -> Void) -> MPRemoteCommandHandlerStatus {
        guard !controller.stations.isEmpty else { return .noSuchContent }
        action(controller)
        return .success
    }

    func update() {
        let center = MPNowPlayingInfoCenter.default()
        guard controller.stationName != nil else {
            center.nowPlayingInfo = nil
            center.playbackState = .stopped
            return
        }
        let info = nowPlayingInfo(controller)
        var values: [String: Any] = [
            MPMediaItemPropertyTitle: info.title,
            MPNowPlayingInfoPropertyIsLiveStream: true,
            MPNowPlayingInfoPropertyMediaType: MPNowPlayingInfoMediaType.audio.rawValue,
        ]
        if let artist = info.artist { values[MPMediaItemPropertyArtist] = artist }
        if info.artwork != coverShown {
            coverShown = info.artwork
            artwork = info.artwork.flatMap { NSImage(contentsOf: $0) }.map { image in
                MPMediaItemArtwork(boundsSize: image.size) { _ in image }
            }
        }
        if let artwork { values[MPMediaItemPropertyArtwork] = artwork }
        center.nowPlayingInfo = values
        center.playbackState = controller.active ? .playing : (controller.status == .stopped ? .stopped : .paused)
    }
}
