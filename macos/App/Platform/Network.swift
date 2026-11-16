import Foundation
import RadioCore

/// The radio's own requests: the directory, covers, logos, Radio 357's titles and update checks.
/// Ten-second timeouts, size limits, and callbacks on the main queue.
enum Network {
    static let userAgent = "MinimalisticRadio/\(appVersion) (macOS)"
    static let coverLimit = 5_000_000
    static let jsonLimit = 5_000_000

    struct TooLarge: Error {}
    struct BadStatus: Error { let code: Int }

    private static func configuration() -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 10
        configuration.httpAdditionalHeaders = ["User-Agent": userAgent]
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        return configuration
    }

    static let session = URLSession(configuration: configuration())

    /// Pictures only: redirects come back as answers, so fetchPicture checks each hop before following it.
    private static let pictureSession = URLSession(configuration: configuration(), delegate: RedirectsAsAnswers(),
                                                   delegateQueue: nil)

    private final class RedirectsAsAnswers: NSObject, URLSessionTaskDelegate {
        func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                        newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
            completionHandler(nil)
        }
    }

    /// At most `limit` bytes; throws on an HTTP error, a larger answer or no connection.
    static func fetchData(_ url: URL, limit: Int) async throws -> Data {
        let (bytes, response) = try await session.bytes(from: url)
        return try await read(bytes, response, limit: limit)
    }

    private static func read(_ bytes: URLSession.AsyncBytes, _ response: URLResponse, limit: Int) async throws -> Data {
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw BadStatus(code: http.statusCode)
        }
        if response.expectedContentLength > limit { throw TooLarge() }
        var data = Data()
        for try await byte in bytes {
            data.append(byte)
            if data.count > limit { throw TooLarge() }
        }
        return data
    }

    /// A picture (logo, favicon, cover, stream artwork) of at most `limit` bytes. Never from the local network:
    /// the address and every redirect (at most 5) must pass `allowed` first. Throws like fetchData, or
    /// PictureRefused.
    static func fetchPicture(_ url: URL, limit: Int,
                             allowed: (URL) async -> Bool = { await pictureAllowed($0) }) async throws -> Data {
        try await followPictureRedirects(url, allowed: allowed) { address in
            let (bytes, response) = try await pictureSession.bytes(from: address)
            if let http = response as? HTTPURLResponse, (300..<400).contains(http.statusCode) {
                return .redirect(http.value(forHTTPHeaderField: "Location"))
            }
            return .data(try await read(bytes, response, limit: limit))
        }
    }

    /// The local-network rule with the system's resolver, off the cooperative threads (getaddrinfo blocks).
    static func pictureAllowed(_ url: URL) async -> Bool {
        await withCheckedContinuation { done in
            DispatchQueue.global(qos: .utility).async {
                done.resume(returning: pictureAddressAllowed(url, resolve: systemResolve))
            }
        }
    }

    /// JSON, or nil on any failure (the controller's FetchJSON).
    static func fetchJSON(_ url: URL, _ done: @escaping (Any?) -> Void) {
        Task {
            let value = try? await json(url)
            await MainActor.run { done(value) }
        }
    }

    /// A cover picture downloaded to `path`, written whole or not at all (the controller's FetchFile).
    static func fetchFile(_ url: URL, _ path: URL, _ done: @escaping (Bool) -> Void) {
        Task {
            var ok = false
            if let data = try? await fetchPicture(url, limit: coverLimit) {
                ok = (try? data.write(to: path, options: .atomic)) != nil
            }
            await MainActor.run { done(ok) }
        }
    }

    /// JSON for the directory search and suggestions (they take an async fetch that throws).
    static func json(_ url: URL) async throws -> Any {
        try JSONSerialization.jsonObject(with: try await fetchData(url, limit: jsonLimit), options: [.fragmentsAllowed])
    }
}
