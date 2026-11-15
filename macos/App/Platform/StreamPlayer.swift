import AVFoundation
import RadioCore

/// The radio's player: AVPlayer behind the controller's AudioPlayer contract.
///
/// - .pls and .m3u station playlists are resolved to their first stream first (AVPlayer plays HLS itself).
/// - Song titles come from the stream's ICY metadata (AVPlayerItemMetadataOutput).
/// - Every callback carries the session it belongs to and is dropped once play() or stop() started another one,
///   and none is delivered from inside play(), stop() or setVolume().
/// - The volume set once stays for the next stations (it lives on the AVPlayer, not the item).
final class StreamPlayer: NSObject, AudioPlayer, AVPlayerItemMetadataOutputPushDelegate {
    let avPlayer = AVPlayer()

    private let onStarted: () -> Void
    private let onTitle: (String) -> Void
    private let onError: (ErrorKind, String) -> Void
    private let onEOS: () -> Void

    private var session = 0
    private var started = false
    private var item: AVPlayerItem?
    private var output: AVPlayerItemMetadataOutput?
    private var observations: [NSKeyValueObservation] = []
    private var notifications: [NSObjectProtocol] = []
    private var stallTimer: Timer?
    private var resolving: Task<Void, Never>?

    /// A stall this long counts as a lost connection.
    private let stallLimit: TimeInterval = 10

    init(onStarted: @escaping () -> Void, onTitle: @escaping (String) -> Void,
         onError: @escaping (ErrorKind, String) -> Void, onEOS: @escaping () -> Void) {
        self.onStarted = onStarted
        self.onTitle = onTitle
        self.onError = onError
        self.onEOS = onEOS
        super.init()
        avPlayer.allowsExternalPlayback = true   // AirPlay
        avPlayer.automaticallyWaitsToMinimizeStalling = true
    }

    func play(_ url: String) {
        tearDown()
        session += 1
        let wanted = session
        resolving = Task { @MainActor [weak self] in
            let resolved = await StreamPlayer.resolve(url)
            guard let self, wanted == self.session else { return }
            switch resolved {
            case .success(let address): self.start(address, wanted)
            case .failure(let failure): self.onError(failure.kind, failure.message)
            }
        }
    }

    func stop() {
        session += 1
        tearDown()
    }

    func setVolume(_ percent: Int) {
        avPlayer.volume = Float(max(0, min(100, percent))) / 100
    }

    // MARK: - Resolving station playlists

    struct Failure: Error {
        let kind: ErrorKind
        let message: String
    }

    /// The address AVPlayer plays: a .pls or .m3u playlist's first stream, anything else as it is.
    private static func resolve(_ url: String) async -> Result<URL, Failure> {
        guard let address = URL(string: url) else {
            return .failure(Failure(kind: .unsupported, message: L("This station uses a format that can't be played.")))
        }
        guard isPlaylistURL(url) else { return .success(address) }
        do {
            let data = try await Network.fetchData(address, limit: 64 * 1024)
            let text = String(decoding: data, as: UTF8.self)
            if isHLS(text) { return .success(address) }
            if let stream = firstStream(text, baseURL: url), let streamURL = URL(string: stream) { return .success(streamURL) }
            return .failure(Failure(kind: .unsupported, message: L("This station uses a format that can't be played.")))
        } catch {
            return .failure(describe(error as NSError, playing: false))
        }
    }

    // MARK: - Playing

    private func start(_ address: URL, _ wanted: Int) {
        let item = AVPlayerItem(asset: AVURLAsset(url: address))
        let output = AVPlayerItemMetadataOutput(identifiers: nil)
        output.setDelegate(self, queue: .main)
        item.add(output)
        self.item = item
        self.output = output
        started = false

        observations = [
            item.observe(\.status) { [weak self] item, _ in
                DispatchQueue.main.async { self?.statusChanged(item, wanted) }
            },
            avPlayer.observe(\.timeControlStatus) { [weak self] player, _ in
                DispatchQueue.main.async { self?.timeControlChanged(player.timeControlStatus, wanted) }
            },
        ]
        let center = NotificationCenter.default
        notifications = [
            center.addObserver(forName: AVPlayerItem.failedToPlayToEndTimeNotification, object: item, queue: .main) { [weak self] note in
                let error = note.userInfo?[AVPlayerItemFailedToPlayToEndTimeErrorKey] as? NSError
                self?.failed(error, wanted)
            },
            center.addObserver(forName: AVPlayerItem.didPlayToEndTimeNotification, object: item, queue: .main) { [weak self] _ in
                guard let self, wanted == self.session else { return }
                self.onEOS()
            },
            center.addObserver(forName: AVPlayerItem.playbackStalledNotification, object: item, queue: .main) { [weak self] _ in
                self?.stalled(wanted)
            },
        ]
        avPlayer.replaceCurrentItem(with: item)
        avPlayer.play()
    }

    private func statusChanged(_ item: AVPlayerItem, _ wanted: Int) {
        guard wanted == session, item.status == .failed else { return }
        failed(item.error as NSError?, wanted)
    }

    private func timeControlChanged(_ status: AVPlayer.TimeControlStatus, _ wanted: Int) {
        guard wanted == session else { return }
        if status == .playing {
            stallTimer?.invalidate()
            stallTimer = nil
            if !started {
                started = true
                onStarted()
            }
        }
    }

    private func stalled(_ wanted: Int) {
        guard wanted == session, stallTimer == nil else { return }
        stallTimer = Timer.scheduledTimer(withTimeInterval: stallLimit, repeats: false) { [weak self] _ in
            guard let self, wanted == self.session else { return }
            self.stallTimer = nil
            if self.avPlayer.timeControlStatus != .playing {
                self.onError(.network, L("The connection to the station was lost."))
            }
        }
    }

    private func failed(_ error: NSError?, _ wanted: Int) {
        guard wanted == session else { return }
        let failure = error.map { StreamPlayer.describe($0, playing: started) }
            ?? Failure(kind: .network, message: L("The connection to the station was lost."))
        tearDown()   // one error per session is enough
        session += 1
        onError(failure.kind, failure.message)
    }

    /// The controller's kind of error and a sentence for the user.
    private static func describe(_ error: NSError, playing: Bool) -> Failure {
        let status = httpStatus(error)
        let kind = classify(domain: error.domain, code: error.code, httpStatus: status)
        switch kind {
        case .refused:
            let text = status.map { L("The station's server refused access ({code}).").replacingOccurrences(of: "{code}", with: String($0)) }
            return Failure(kind: kind, message: text ?? L("The station's server refused access."))
        case .unsupported:
            return Failure(kind: kind, message: L("This station uses a format that can't be played."))
        case .network:
            if let status, status >= 400 {
                return Failure(kind: kind, message: L("The station's server returned error {code}.").replacingOccurrences(of: "{code}", with: String(status)))
            }
            return Failure(kind: kind, message: playing ? L("The connection to the station was lost.")
                                                        : L("Couldn't connect to the station. Check your internet connection."))
        }
    }

    /// An HTTP status hidden in AVFoundation's error ("HTTP 404"), in the error or its underlying ones.
    private static func httpStatus(_ error: NSError) -> Int? {
        var current: NSError? = error
        while let checked = current {
            let text = [checked.localizedDescription, checked.localizedFailureReason ?? "", "\(checked.userInfo)"].joined(separator: " ")
            if let range = text.range(of: #"HTTP (\d{3})"#, options: .regularExpression) {
                return Int(text[range].dropFirst(5))
            }
            current = checked.userInfo[NSUnderlyingErrorKey] as? NSError
        }
        return nil
    }

    // MARK: - Song titles

    func metadataOutput(_ output: AVPlayerItemMetadataOutput, didOutputTimedMetadataGroups groups: [AVTimedMetadataGroup],
                        from track: AVPlayerItemTrack?) {
        guard output === self.output else { return }
        for group in groups {
            for item in group.items {
                guard item.identifier == .icyMetadataStreamTitle || item.identifier == .commonIdentifierTitle,
                      let title = item.stringValue else { continue }
                onTitle(title)
                return
            }
        }
    }

    // MARK: - Clearing up

    private func tearDown() {
        resolving?.cancel()
        resolving = nil
        stallTimer?.invalidate()
        stallTimer = nil
        observations.forEach { $0.invalidate() }
        observations = []
        notifications.forEach { NotificationCenter.default.removeObserver($0) }
        notifications = []
        output?.setDelegate(nil, queue: nil)
        output = nil
        item = nil
        avPlayer.pause()
        avPlayer.replaceCurrentItem(with: nil)
    }
}
