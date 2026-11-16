import CoreGraphics
import Darwin
import Foundation
import ImageIO

// Pictures from outside: station logos, radio-browser favicons, share-link logos, song covers and stream artwork
// (docs/superpowers/specs/2026-11-16-security-hardening-design.md, sections 2 and 3). They are never fetched from
// the local network, redirects are followed here so every hop is checked, and nothing whose header declares more
// than 4096 pixels either way is decoded. A refused picture behaves like one that failed to load. Streams are not
// affected: a station on the home network still plays.

// MARK: - The local network

/// The addresses a host name resolves to, as text ("93.184.216.34", "2606:2800:220:1::1"); nil when it doesn't.
public typealias ResolveHost = (String) -> [String]?

private let localSuffixes = [".localhost", ".local", ".lan", ".home", ".internal", ".home.arpa"]

/// A picture may be fetched from `url`: http or https, not a local name, and neither the host nor any address it
/// resolves to is loopback, private, link-local, carrier-grade NAT, multicast, unspecified or reserved. Names are
/// resolved with `resolve` (IP addresses and local names are decided without it); one that doesn't resolve is
/// refused.
public func pictureAddressAllowed(_ url: URL, resolve: ResolveHost) -> Bool {
    guard isWebURL(url.absoluteString),
          let raw = URLComponents(url: url, resolvingAgainstBaseURL: true)?.host else { return false }
    let host = bareHost(raw)
    if host.isEmpty || host == "localhost" || localSuffixes.contains(where: { host.hasSuffix($0) }) { return false }
    if let address = ipAddress(host) { return !isLocalAddress(address) }
    guard let addresses = resolve(host), !addresses.isEmpty else { return false }
    return addresses.allSatisfy { ipAddress(bareHost($0)).map { !isLocalAddress($0) } ?? false }
}

/// Lowercase, without IPv6 brackets, an IPv6 zone ("%en0") or trailing dots.
private func bareHost(_ host: String) -> String {
    var text = host.lowercased()
    if text.hasPrefix("[") && text.hasSuffix("]") { text = String(text.dropFirst().dropLast()) }
    if let zone = text.firstIndex(of: "%") { text = String(text[..<zone]) }
    while text.hasSuffix(".") { text.removeLast() }
    return text
}

/// The 4 or 16 bytes of an IPv4 or IPv6 address written the standard way; nil for a name.
private func ipAddress(_ text: String) -> [UInt8]? {
    var v4 = in_addr()
    if inet_pton(AF_INET, text, &v4) == 1 { return withUnsafeBytes(of: &v4) { Array($0) } }
    var v6 = in6_addr()
    if inet_pton(AF_INET6, text, &v6) == 1 { return withUnsafeBytes(of: &v6) { Array($0) } }
    return nil
}

private func isLocalAddress(_ bytes: [UInt8]) -> Bool {
    bytes.count == 4 ? isLocalIPv4(bytes) : isLocalIPv6(bytes)
}

/// 0/8, 10/8, 100.64/10, 127/8, 169.254/16, 172.16/12, 192.0.0/24, 192.168/16, 198.18/15, 224/4 and 240/4.
private func isLocalIPv4(_ b: [UInt8]) -> Bool {
    switch b[0] {
    case 0, 10, 127: return true
    case 100: return b[1] & 0xC0 == 64
    case 169: return b[1] == 254
    case 172: return b[1] & 0xF0 == 16
    case 192: return b[1] == 168 || (b[1] == 0 && b[2] == 0)
    case 198: return b[1] & 0xFE == 18
    default: return b[0] >= 224
    }
}

/// ::, ::1, fc00::/7, fe80::/10, and the IPv4-mapped forms (::ffff:a.b.c.d) of the IPv4 ranges.
private func isLocalIPv6(_ b: [UInt8]) -> Bool {
    if b[0..<10].allSatisfy({ $0 == 0 }) && b[10] == 0xFF && b[11] == 0xFF { return isLocalIPv4(Array(b[12..<16])) }
    if b[0..<15].allSatisfy({ $0 == 0 }) && b[15] <= 1 { return true }
    return b[0] & 0xFE == 0xFC || (b[0] == 0xFE && b[1] & 0xC0 == 0x80)
}

/// The system's answer for a host name (getaddrinfo), as text; nil when it doesn't resolve. Blocks: call it off the
/// main thread.
public func systemResolve(_ host: String) -> [String]? {
    var hints = addrinfo()
    hints.ai_family = AF_UNSPEC
    hints.ai_socktype = SOCK_STREAM
    var first: UnsafeMutablePointer<addrinfo>?
    guard getaddrinfo(host, nil, &hints, &first) == 0, let first else { return nil }
    defer { freeaddrinfo(first) }
    var addresses: [String] = []
    for info in sequence(first: first, next: { $0.pointee.ai_next }) {
        guard let address = info.pointee.ai_addr else { continue }
        var text = [CChar](repeating: 0, count: Int(NI_MAXHOST))
        if getnameinfo(address, info.pointee.ai_addrlen, &text, socklen_t(text.count), nil, 0, NI_NUMERICHOST) == 0 {
            addresses.append(String(cString: text))
        }
    }
    return addresses
}

// MARK: - Redirects

/// Redirects followed for a picture, each one checked like the first address.
public let pictureRedirectsFollowed = 5

/// One answer to a picture request made without following redirects.
public enum PictureAnswer: Sendable {
    /// A 3xx answer and its Location header.
    case redirect(String?)
    case data(Data)
}

/// The address, or a redirect hop, may not be fetched; or there were too many redirects.
public struct PictureRefused: Error {}

/// Where a redirect leads: its Location resolved against the address that answered, only when it is http(s).
public func redirectTarget(_ location: String?, from: URL) -> URL? {
    guard let location, let target = URL(string: location, relativeTo: from)?.absoluteURL,
          isWebURL(target.absoluteString) else { return nil }
    return target
}

/// A picture from `url`: every address, the first and each redirect (at most 5), is checked with `allowed` before
/// `get` asks for it.
public func followPictureRedirects(_ url: URL, allowed: (URL) async -> Bool,
                                   get: (URL) async throws -> PictureAnswer) async throws -> Data {
    var address = url
    var redirects = 0
    while true {
        guard await allowed(address) else { throw PictureRefused() }
        switch try await get(address) {
        case .data(let data):
            return data
        case .redirect(let location):
            redirects += 1
            guard redirects <= pictureRedirectsFollowed, let next = redirectTarget(location, from: address) else {
                throw PictureRefused()
            }
            address = next
        }
    }
}

// MARK: - 4096 pixels

/// Pictures declared wider or taller than this are never decoded.
public let picturePixelLimit = 4096

public func pictureSizeAllowed(width: Int, height: Int) -> Bool {
    width > 0 && height > 0 && width <= picturePixelLimit && height <= picturePixelLimit
}

/// Width and height as the picture's header declares them (CGImageSourceCopyPropertiesAtIndex reads the header
/// without decoding the pixels); nil when they can't be read.
public func declaredPictureSize(_ data: Data) -> (width: Int, height: Int)? {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
    return declaredSize(source)
}

private func declaredSize(_ source: CGImageSource) -> (width: Int, height: Int)? {
    guard CGImageSourceGetCount(source) > 0,
          let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
          let width = (properties[kCGImagePropertyPixelWidth] as? NSNumber)?.intValue,
          let height = (properties[kCGImagePropertyPixelHeight] as? NSNumber)?.intValue else { return nil }
    return (width, height)
}

/// A downloaded picture (PNG, JPEG, GIF, ICO, WebP…) decoded at most `maxPixels` on its longer side; nil when it
/// isn't a picture, its size can't be read, or its header declares more than 4096 pixels either way.
public func decodePicture(_ data: Data, maxPixels: Int) -> CGImage? {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil), let size = declaredSize(source),
          pictureSizeAllowed(width: size.width, height: size.height) else { return nil }
    if max(size.width, size.height) <= maxPixels { return CGImageSourceCreateImageAtIndex(source, 0, nil) }
    let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                    kCGImageSourceThumbnailMaxPixelSize: maxPixels,
                                    kCGImageSourceCreateThumbnailWithTransform: true]
    return CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
}
