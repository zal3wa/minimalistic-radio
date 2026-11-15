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

    static let session: URLSession = {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 10
        configuration.httpAdditionalHeaders = ["User-Agent": userAgent]
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: configuration)
    }()

    /// At most `limit` bytes; throws on an HTTP error, a larger answer or no connection.
    static func fetchData(_ url: URL, limit: Int) async throws -> Data {
        let (bytes, response) = try await session.bytes(from: url)
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

    /// JSON, or nil on any failure (the controller's FetchJSON).
    static func fetchJSON(_ url: URL, _ done: @escaping (Any?) -> Void) {
        Task {
            let value = try? await json(url)
            await MainActor.run { done(value) }
        }
    }

    /// A download to `path`, written whole or not at all (the controller's FetchFile).
    static func fetchFile(_ url: URL, _ path: URL, _ done: @escaping (Bool) -> Void) {
        Task {
            var ok = false
            if let data = try? await fetchData(url, limit: coverLimit) {
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
