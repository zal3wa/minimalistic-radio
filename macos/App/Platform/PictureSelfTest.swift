import AppKit
import Network
import RadioCore

/// `--self-test`: pictures are fetched only as the rules say, on this Mac's own network stack. A tiny HTTP server on
/// 127.0.0.1 answers /hop/N with a redirect to /hop/N-1, and /hop/0 or /local with a picture. Nothing leaves the
/// computer. Network.fetchPicture must follow at most 5 redirects itself, check every hop, and never ask a local
/// address.
@MainActor
enum PictureSelfTest {
    static func run() -> [String] {
        var failures: [String] = []
        for address in ["http://localhost/logo.png", "http://127.0.0.1/logo.png", "http://[::1]/logo.png",
                        "http://printer.local/logo.png", "http://192.168.1.1/logo.png"]
            where pictureAddressAllowed(URL(string: address)!, resolve: systemResolve) {
            failures.append("a picture from \(address) would be fetched")
        }
        if LogoCache.decode(png(width: 4097, height: 1)) != nil { failures.append("a picture wider than 4096 pixels is decoded") }
        if LogoCache.decode(png(width: 300, height: 200))?.size != NSSize(width: 144, height: 96) {
            failures.append("a logo isn't decoded small")
        }

        guard let server = LoopbackServer(), let port = server.waitForPort() else {
            return failures + ["the self-test's picture server didn't start"]
        }
        defer { server.stop() }
        let base = "http://127.0.0.1:\(port)"
        let picture = Data("picture".utf8)
        func fetch(_ path: String, allowed: @escaping (URL) async -> Bool = { _ in true }) -> Data? {
            wait { try? await Network.fetchPicture(URL(string: base + path)!, limit: 1000, allowed: allowed) }
        }
        if fetch("/hop/5") != picture { failures.append("a picture behind 5 redirects doesn't load") }
        if fetch("/hop/6") != nil { failures.append("a picture behind 6 redirects loads") }
        let before = server.paths.count
        if fetch("/hop/3", allowed: { $0.path != "/hop/1" }) != nil { failures.append("a refused redirect hop is followed") }
        let asked = Array(server.paths.dropFirst(before))
        if asked != ["/hop/3", "/hop/2"] { failures.append("redirect hops aren't checked before they are asked (\(asked))") }
        if fetch("/local", allowed: { await Network.pictureAllowed($0) }) != nil || server.paths.contains("/local") {
            failures.append("a picture is fetched from 127.0.0.1")
        }
        return failures
    }

    private static func png(width: Int, height: Int) -> Data {
        let pixels = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8,
                                      samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                                      bytesPerRow: 0, bitsPerPixel: 0)
        return pixels?.representation(using: .png, properties: [:]) ?? Data()
    }

    /// Runs `work` off the main thread while the main run loop keeps going; nil after 20 seconds.
    private static func wait<T>(_ work: @escaping () async -> T?) -> T? {
        let box = Box<T>()
        Task.detached {
            let value = await work()
            await MainActor.run {
                box.value = value
                box.done = true
            }
        }
        let deadline = Date().addingTimeInterval(20)
        while !box.done && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.05)) }
        return box.value
    }
}

private final class Box<T> {
    var value: T?
    var done = false
}

/// HTTP/1.1 on 127.0.0.1, one request per connection: /hop/N redirects to /hop/N-1, anything else is the picture.
private final class LoopbackServer {
    private let listener: NWListener
    private let queue = DispatchQueue(label: "io.github.zal3wa.minimalistic-radio.self-test-server")
    private var asked: [String] = []

    init?() {
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)
        guard let listener = try? NWListener(using: parameters) else { return nil }
        self.listener = listener
        listener.newConnectionHandler = { [weak self] connection in
            guard let self else { return }
            connection.start(queue: self.queue)
            connection.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { data, _, _, _ in
                let request = String(decoding: data ?? Data(), as: UTF8.self)
                let path = request.split(separator: " ").dropFirst().first.map(String.init) ?? "/"
                self.asked.append(path)
                let left = path.hasPrefix("/hop/") ? Int(path.dropFirst(5)) ?? 0 : 0
                let reply = left > 0
                    ? "HTTP/1.1 302 Found\r\nLocation: /hop/\(left - 1)\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    : "HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: 7\r\nConnection: close\r\n\r\npicture"
                connection.send(content: Data(reply.utf8), completion: .contentProcessed { _ in connection.cancel() })
            }
        }
        listener.start(queue: queue)
    }

    /// The paths asked so far.
    var paths: [String] { queue.sync { asked } }

    /// The port once the listener is ready; nil after 5 seconds.
    func waitForPort() -> UInt16? {
        let deadline = Date().addingTimeInterval(5)
        while Date() < deadline {
            if let port = listener.port, port.rawValue != 0 { return port.rawValue }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        return nil
    }

    func stop() {
        listener.cancel()
    }
}
