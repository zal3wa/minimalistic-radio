import CoreGraphics
import Foundation
import ImageIO
import Testing
@testable import RadioCore

// Pictures from outside (logos, favicons, share-link logos, covers, stream artwork): never from the local network,
// redirects checked hop by hop, and nothing declared bigger than 4096 pixels is decoded.

// MARK: - The local network

/// A resolver that knows a few names and remembers what it was asked.
private final class FakeResolver {
    var asked: [String] = []
    let answers: [String: [String]] = [
        "cdn.example.com": ["93.184.216.34", "2606:2800:220:1::1"],
        "rebind.example": ["192.168.0.10"],
        "mixed.example": ["93.184.216.34", "10.0.0.7"],
        "mapped.example": ["::ffff:127.0.0.1"],
        "zone.example": ["fe80::1%en0"],
        "nothing.example": [],
    ]

    func resolve(_ host: String) -> [String]? {
        asked.append(host)
        return answers[host]
    }
}

private func allowed(_ address: String, _ resolver: FakeResolver = FakeResolver()) -> Bool {
    guard let url = URL(string: address) else { return false }
    return pictureAddressAllowed(url, resolve: resolver.resolve)
}

@Test(arguments: [
    "http://localhost/logo.png", "http://LOCALHOST./logo.png", "http://app.localhost/logo.png",
    "http://127.0.0.1/logo.png", "http://127.8.9.10:8080/logo.png", "http://10.1.2.3/logo.png",
    "http://192.168.1.1/logo.png", "http://172.16.0.1/logo.png", "http://172.31.255.255/logo.png",
    "http://169.254.169.254/latest/meta-data", "http://100.64.0.1/logo.png", "http://100.127.255.255/logo.png",
    "http://0.0.0.0/logo.png", "http://0.1.2.3/logo.png", "http://224.0.0.1/logo.png", "http://239.255.255.250/x",
    "http://240.0.0.1/logo.png", "http://255.255.255.255/logo.png", "http://192.0.0.8/logo.png",
    "http://198.18.0.1/logo.png", "http://198.19.255.255/logo.png",
    "http://[::1]/logo.png", "http://[::]/logo.png", "http://[fe80::1]/logo.png", "http://[febf::1]/logo.png",
    "http://[fc00::1]/logo.png", "http://[fd12:3456::1]/logo.png", "http://[::ffff:192.168.1.1]/logo.png",
    "http://[::ffff:7f00:1]/logo.png",
    "http://printer.local/logo.png", "http://NAS.LAN/logo.png", "http://router.home.arpa/logo.png",
    "http://box.home/logo.png", "http://service.internal/logo.png", "http://router.lan./logo.png",
    "ftp://cdn.example.com/logo.png", "file:///etc/hosts", "data:image/png;base64,AAAA", "/relative/logo.png",
])
func localAddressesAreRefused(address: String) {
    let resolver = FakeResolver()
    #expect(!allowed(address, resolver))
    #expect(resolver.asked.isEmpty)   // decided without asking DNS
}

@Test(arguments: [
    "https://8.8.8.8/logo.png", "http://1.1.1.1/logo.png", "https://[2606:4700::1111]/logo.png",
    "http://172.32.0.1/logo.png", "http://172.15.255.255/logo.png", "http://100.128.0.1/logo.png",
    "http://100.63.255.255/logo.png", "http://192.169.0.1/logo.png", "http://169.255.0.1/logo.png",
    "http://198.20.0.1/logo.png", "http://223.255.255.255/logo.png", "http://11.0.0.1/logo.png",
    "http://[fec0::1]/logo.png", "http://[::ffff:8.8.8.8]/logo.png",
])
func publicAddressesPass(address: String) {
    #expect(allowed(address))
}

@Test func publicNamePasses() {
    let resolver = FakeResolver()
    #expect(allowed("https://cdn.example.com/logos/a.png", resolver))
    #expect(resolver.asked == ["cdn.example.com"])
    #expect(allowed("https://CDN.example.com./logos/a.png"))
}

@Test func nameResolvingToALocalAddressIsRefused() {
    #expect(!allowed("http://rebind.example/a.png"))
    #expect(!allowed("http://mixed.example/a.png"))      // one local answer is enough
    #expect(!allowed("http://mapped.example/a.png"))
    #expect(!allowed("http://zone.example/a.png"))
}

@Test func nameThatDoesNotResolveIsRefused() {
    #expect(!allowed("http://nothing.example/a.png"))
    #expect(!allowed("http://unknown.example/a.png"))
}

@Test func systemResolverKnowsLocalhost() {
    let addresses = systemResolve("localhost") ?? []
    #expect(addresses.contains { $0 == "127.0.0.1" || $0.hasPrefix("::1") })
    #expect(!pictureAddressAllowed(URL(string: "http://127.0.0.1/logo.png")!, resolve: systemResolve))
    #expect(!pictureAddressAllowed(URL(string: "http://0x7f.1/logo.png")!, resolve: systemResolve))   // 127.0.0.1 in disguise
}

// MARK: - Redirects

@Test func redirectTargetsAreResolvedAndMustBeWebAddresses() {
    let from = URL(string: "http://a.example/logos/x.png")!
    #expect(redirectTarget("https://b.example/y.png", from: from)?.absoluteString == "https://b.example/y.png")
    #expect(redirectTarget("/z.png", from: from)?.absoluteString == "http://a.example/z.png")
    #expect(redirectTarget("w.png", from: from)?.absoluteString == "http://a.example/logos/w.png")
    #expect(redirectTarget("ftp://b.example/y.png", from: from) == nil)
    #expect(redirectTarget("file:///etc/passwd", from: from) == nil)
    #expect(redirectTarget(nil, from: from) == nil)
}

/// A web of addresses: /hop/N redirects to /hop/N-1, /hop/0 is the picture.
private final class FakeWeb {
    var requested: [String] = []
    var checked: [String] = []
    var refused: Set<String> = []

    func allowed(_ url: URL) async -> Bool {
        checked.append(url.path)
        return !refused.contains(url.path)
    }

    func get(_ url: URL) async throws -> PictureAnswer {
        requested.append(url.path)
        if url.path == "/away" { return .redirect("ftp://elsewhere.example/x") }
        let left = Int(url.lastPathComponent) ?? 0
        return left > 0 ? .redirect("/hop/\(left - 1)") : .data(Data("picture".utf8))
    }

    func fetch(_ path: String) async throws -> Data {
        try await followPictureRedirects(URL(string: "https://pictures.example" + path)!, allowed: self.allowed, get: self.get)
    }
}

@Test func fiveRedirectsAreFollowed() async throws {
    let web = FakeWeb()
    #expect(try await web.fetch("/hop/5") == Data("picture".utf8))
    #expect(web.requested == ["/hop/5", "/hop/4", "/hop/3", "/hop/2", "/hop/1", "/hop/0"])
    #expect(web.checked == web.requested)   // every hop checked before it is asked
}

@Test func aSixthRedirectFails() async {
    let web = FakeWeb()
    await #expect(throws: PictureRefused.self) { try await web.fetch("/hop/6") }
    #expect(web.requested.count == 6)
}

@Test func aRefusedHopIsNeverAsked() async {
    let web = FakeWeb()
    web.refused = ["/hop/1"]
    await #expect(throws: PictureRefused.self) { try await web.fetch("/hop/3") }
    #expect(web.requested == ["/hop/3", "/hop/2"])
    let first = FakeWeb()
    first.refused = ["/hop/0"]
    await #expect(throws: PictureRefused.self) { try await first.fetch("/hop/0") }
    #expect(first.requested.isEmpty)
}

@Test func aRedirectToAnotherSchemeFails() async {
    let web = FakeWeb()
    await #expect(throws: PictureRefused.self) { try await web.fetch("/away") }
    #expect(web.requested == ["/away"])
}

// MARK: - 4096 pixels

/// A PNG of `width` × `height`, encoded for real.
private func png(_ width: Int, _ height: Int) -> Data {
    let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    context.setFillColor(CGColor(red: 1, green: 0, blue: 0, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    let data = NSMutableData()
    let destination = CGImageDestinationCreateWithData(data as CFMutableData, "public.png" as CFString, 1, nil)!
    CGImageDestinationAddImage(destination, context.makeImage()!, nil)
    CGImageDestinationFinalize(destination)
    return data as Data
}

@Test func sizeLimitIs4096EachWay() {
    #expect(pictureSizeAllowed(width: 4096, height: 4096))
    #expect(pictureSizeAllowed(width: 1, height: 1))
    #expect(!pictureSizeAllowed(width: 4097, height: 16))
    #expect(!pictureSizeAllowed(width: 16, height: 4097))
    #expect(!pictureSizeAllowed(width: 0, height: 16))
}

@Test func sizeIsReadFromTheHeader() {
    #expect(declaredPictureSize(png(4097, 1)).map { [$0.width, $0.height] } == [4097, 1])
    #expect(declaredPictureSize(png(3, 4100)).map { [$0.width, $0.height] } == [3, 4100])
    #expect(declaredPictureSize(Data("<html>not a picture</html>".utf8)) == nil)
}

@Test func picturesDeclaredBiggerThan4096AreRefused() {
    #expect(decodePicture(png(4097, 1), maxPixels: 144) == nil)
    #expect(decodePicture(png(1, 4097), maxPixels: 600) == nil)
    #expect(decodePicture(Data("<html>not a picture</html>".utf8), maxPixels: 144) == nil)
    #expect(decodePicture(Data(), maxPixels: 144) == nil)
}

@Test func picturesAreDecodedSmall() {
    let small = decodePicture(png(16, 16), maxPixels: 144)
    #expect(small?.width == 16 && small?.height == 16)
    let wide = decodePicture(png(4096, 1024), maxPixels: 600)
    #expect(wide?.width == 600 && wide?.height == 150)
}
