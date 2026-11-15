import Foundation

// Stream address rules, mirroring IsWebUrl and StreamKey in src/Services/Storage.cs (and linux/core/streams.py).

private let defaultPorts = ["http": 80, "https": 443]

public func isWebURL(_ value: String?) -> Bool {
    guard let value, !value.isEmpty, let parts = URLComponents(string: value),
          let scheme = parts.scheme?.lowercased(), defaultPorts[scheme] != nil,
          let host = parts.host, !host.isEmpty else { return false }
    return parts.user == nil && parts.password == nil
}

/// The same station whatever the scheme, the letter case of the host, a default port or a trailing slash.
public func streamKey(_ url: String?) -> String {
    let text = (url ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    guard let parts = URLComponents(string: text), let scheme = parts.scheme?.lowercased(),
          let host = parts.host, !host.isEmpty else { return text }
    var key = host.lowercased()
    if let port = parts.port, port != defaultPorts[scheme] { key += ":\(port)" }
    var path = parts.percentEncodedPath
    while path.hasSuffix("/") { path.removeLast() }
    key += path
    if let query = parts.percentEncodedQuery, !query.isEmpty { key += "?" + query }
    return key
}

public func sameStream(_ a: String?, _ b: String?) -> Bool {
    streamKey(a) == streamKey(b)
}
