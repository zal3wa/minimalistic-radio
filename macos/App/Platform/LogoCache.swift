import AppKit
import CryptoKit
import ImageIO
import RadioCore

/// Station logos: downloaded once into the cache folder, decoded small off the main thread, kept in memory.
/// A port of linux/minimalistic_radio/ui/logos.py. Keeping the decoded pictures means a redrawn list (a station
/// added, moved or renamed) never shows a logo going blank for a moment.
@MainActor
final class LogoCache {
    static let logoLimit = 2_000_000      // bytes downloaded at most
    static let logoPixels = 96            // decoded at most this big: shown at 40 pt, sharp at 2×
    static let retrySeconds: TimeInterval = 300
    static let maxDownloads = 4

    let folder: URL
    private var images: [String: NSImage?] = [:]
    private var failed: [String: Date] = [:]
    private var waiting: [String: [(NSImage?) -> Void]] = [:]
    private var queued: [String] = []
    private var running = 0

    init(folder: URL) {
        self.folder = folder
    }

    /// (known, image). Known with nil: there is no logo to show (none, not a web address, not a picture).
    func lookup(_ url: String?) -> (known: Bool, image: NSImage?) {
        guard let url, isWebURL(url) else { return (true, nil) }
        if let image = images[url] { return (true, image) }
        if let when = failed[url], Date().timeIntervalSince(when) < Self.retrySeconds { return (true, nil) }
        return (false, nil)
    }

    /// Fetches a logo that lookup() doesn't know yet, and calls back on the main thread.
    func load(_ url: String, _ done: @escaping (NSImage?) -> Void) {
        guard isWebURL(url) else { return done(nil) }
        if waiting[url] != nil {
            waiting[url]?.append(done)
            return
        }
        waiting[url] = [done]
        queued.append(url)
        startNext()
    }

    private func startNext() {
        while running < Self.maxDownloads, !queued.isEmpty {
            let url = queued.removeFirst()
            running += 1
            let file = folder.appendingPathComponent(Self.fileName(url))
            Task.detached(priority: .utility) {
                let (image, downloaded) = await LogoCache.read(url, file)
                await MainActor.run { self.deliver(url, image, downloaded) }
            }
        }
    }

    private func deliver(_ url: String, _ image: NSImage?, _ downloaded: Bool) {
        running -= 1
        if downloaded {
            images[url] = .some(image)
            failed[url] = nil
        } else {
            failed[url] = Date()
        }
        for done in waiting.removeValue(forKey: url) ?? [] { done(image) }
        startNext()
    }

    static func fileName(_ url: String) -> String {
        Insecure.SHA1.hash(data: Data(url.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    /// (image, whether the download worked). The cached file first, then the network.
    nonisolated private static func read(_ url: String, _ file: URL) async -> (NSImage?, Bool) {
        if let data = try? Data(contentsOf: file), let image = decode(data) { return (image, true) }
        guard let address = URL(string: url), let data = try? await Network.fetchData(address, limit: logoLimit) else {
            return (nil, false)
        }
        let image = decode(data)
        if image != nil {
            try? FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? data.write(to: file, options: .atomic)
        }
        return (image, true)
    }

    /// PNG, JPEG, GIF, ICO, WebP… made at most `logoPixels` on the longer side; nil if it isn't a picture.
    nonisolated static func decode(_ data: Data, maxPixels: Int = logoPixels) -> NSImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil), CGImageSourceGetCount(source) > 0 else { return nil }
        let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        let width = properties?[kCGImagePropertyPixelWidth] as? Int ?? 0
        let height = properties?[kCGImagePropertyPixelHeight] as? Int ?? 0
        let image: CGImage?
        if width > 0 && height > 0 && max(width, height) <= maxPixels {
            image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        } else {
            let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                            kCGImageSourceThumbnailMaxPixelSize: maxPixels,
                                            kCGImageSourceCreateThumbnailWithTransform: true]
            image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
        }
        guard let image else { return nil }
        return NSImage(cgImage: image, size: NSSize(width: image.width, height: image.height))
    }
}
