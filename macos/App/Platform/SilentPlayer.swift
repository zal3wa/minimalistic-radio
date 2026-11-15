import RadioCore

/// A player that plays nothing: for the self-test and the screenshots.
final class SilentPlayer: AudioPlayer {
    func play(_ url: String) {}
    func stop() {}
    func setVolume(_ percent: Int) {}
}
