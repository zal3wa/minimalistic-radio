import Foundation

// Self-updates, as on Windows but for the Mac's own releases: tags macos-vX.Y.Z (betas macos-vX.Y.Z-beta.N).
// Mac releases are never "latest" on GitHub, so the app reads the list of releases and picks its own.

public let releasesURL = URL(string: "https://api.github.com/repos/zal3wa/minimalistic-radio/releases?per_page=30")!
public let updateCheckInterval: TimeInterval = 6 * 3600
public let updateZipName = "Minimalistic-Radio-macOS.zip"
public let updateDMGName = "Minimalistic-Radio.dmg"

private let tagPattern = try! NSRegularExpression(pattern: #"^macos-v(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$"#)

public struct ReleaseTag: Comparable, Sendable {
    public let major: Int
    public let minor: Int
    public let patch: Int
    /// nil for a full release.
    public let beta: Int?

    /// "macos-v1.2.3" or "macos-v1.2.3-beta.4"; nil for anything else ("dev", Windows and Linux tags).
    public init?(_ tag: String) {
        let range = NSRange(tag.startIndex..., in: tag)
        guard let match = tagPattern.firstMatch(in: tag, range: range) else { return nil }
        func number(_ index: Int) -> Int? {
            Range(match.range(at: index), in: tag).flatMap { Int(tag[$0]) }
        }
        guard let major = number(1), let minor = number(2), let patch = number(3) else { return nil }
        self.major = major
        self.minor = minor
        self.patch = patch
        self.beta = number(4)
    }

    public static func < (a: ReleaseTag, b: ReleaseTag) -> Bool {
        if (a.major, a.minor, a.patch) != (b.major, b.minor, b.patch) {
            return (a.major, a.minor, a.patch) < (b.major, b.minor, b.patch)
        }
        switch (a.beta, b.beta) {
        case let (x?, y?): return x < y
        case (.some, nil): return true    // a beta comes before its release
        default: return false
        }
    }
}

public struct AvailableUpdate: Equatable, Sendable {
    public let tag: ReleaseTag
    public let tagName: String
    public let zip: URL
    public let dmg: URL
    public let page: URL
}

/// The newest Mac release newer than `current`, from the GitHub API's list of releases. Drafts, other systems'
/// tags and releases missing a file are skipped; betas are offered only to a beta.
public func newestUpdate(releases: Any?, current: ReleaseTag) -> AvailableUpdate? {
    var best: AvailableUpdate?
    for case let release as [String: Any] in releases as? [Any] ?? [] {
        guard release["draft"] as? Bool != true, let name = release["tag_name"] as? String,
              let tag = ReleaseTag(name), tag > current, tag.beta == nil || current.beta != nil else { continue }
        var files: [String: URL] = [:]
        for case let asset as [String: Any] in release["assets"] as? [Any] ?? [] {
            if let file = asset["name"] as? String, let link = asset["browser_download_url"] as? String,
               let url = URL(string: link) {
                files[file] = url
            }
        }
        guard let zip = files[updateZipName], let dmg = files[updateDMGName],
              let page = (release["html_url"] as? String).flatMap(URL.init(string:)) else { continue }
        if best == nil || best!.tag < tag {
            best = AvailableUpdate(tag: tag, tagName: name, zip: zip, dmg: dmg, page: page)
        }
    }
    return best
}

public func updateCheckDue(last: Date?, now: Date) -> Bool {
    guard let last else { return true }
    return now.timeIntervalSince(last) >= updateCheckInterval
}

/// The app can replace itself only in a writable folder, not from the DMG or a translocated copy (an app opened
/// from Downloads runs from a random read-only path until it is moved).
public func canSwapInPlace(bundlePath: String, writable: Bool) -> Bool {
    if bundlePath.hasPrefix("/Volumes/") || bundlePath.contains("/AppTranslocation/") { return false }
    return writable
}

public enum UpdateState: Equatable, Sendable {
    case none
    case available(AvailableUpdate)
    case downloading(Int)
    case failed
}

/// The state after a check: a failed check (offline) changes nothing, and a download in progress stays.
public func afterCheck(_ result: AvailableUpdate?, fetchFailed: Bool, previous: UpdateState) -> UpdateState {
    if case .downloading = previous { return previous }
    if fetchFailed { return previous }
    return result.map(UpdateState.available) ?? UpdateState.none
}
