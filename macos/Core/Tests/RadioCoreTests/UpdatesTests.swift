import Foundation
import Testing
@testable import RadioCore

private let project = "https://github.com/zal3wa/minimalistic-radio/releases/"

private func asset(_ tag: String, _ name: String) -> [String: Any] {
    ["name": name, "browser_download_url": project + "download/\(tag)/\(name)"]
}

private func release(_ tag: String, draft: Bool = false, zip: Bool = true) -> [String: Any] {
    var assets = [asset(tag, "Minimalistic-Radio.dmg")]
    if zip { assets.append(asset(tag, "Minimalistic-Radio-macOS.zip")) }
    return ["tag_name": tag, "draft": draft, "html_url": project + "tag/\(tag)", "assets": assets]
}

private let releases: [[String: Any]] = [
    release("v2.5.0"), release("linux-v1.0.0-beta.5"), release("macos-download"), release("macos-v1.0.2", draft: true),
    release("macos-v1.0.1-beta.1"), release("macos-v1.0.0"),
]

@Test func betaSortsBeforeRelease() {
    #expect(ReleaseTag("macos-v1.0.0-beta.2")! < ReleaseTag("macos-v1.0.0")!)
    #expect(ReleaseTag("macos-v1.0.0-beta.2")! < ReleaseTag("macos-v1.0.0-beta.10")!)
    #expect(ReleaseTag("macos-v1.2.3")! < ReleaseTag("macos-v1.10.0")!)
    #expect(ReleaseTag("dev") == nil && ReleaseTag("v2.5.0") == nil && ReleaseTag("macos-download") == nil)
}

@Test func newestSkipsOtherSystemsDraftsAndBetasForStableUsers() {
    #expect(newestUpdate(releases: releases, current: ReleaseTag("macos-v0.9.0")!)?.tagName == "macos-v1.0.0")
    #expect(newestUpdate(releases: releases, current: ReleaseTag("macos-v1.0.0-beta.3")!)?.tagName == "macos-v1.0.1-beta.1")
    #expect(newestUpdate(releases: releases, current: ReleaseTag("macos-v1.0.0")!) == nil)
    let update = newestUpdate(releases: releases, current: ReleaseTag("macos-v0.9.0")!)
    #expect(update?.zip.absoluteString == project + "download/macos-v1.0.0/Minimalistic-Radio-macOS.zip")
    #expect(update?.dmg.absoluteString == project + "download/macos-v1.0.0/Minimalistic-Radio.dmg")
    #expect(update?.page.absoluteString == project + "tag/macos-v1.0.0")
}

@Test func releaseWithoutTheZipIsSkipped() {
    #expect(newestUpdate(releases: [release("macos-v2.0.0", zip: false)], current: ReleaseTag("macos-v1.0.0")!) == nil)
    #expect(newestUpdate(releases: "not a list", current: ReleaseTag("macos-v1.0.0")!) == nil)
}

@Test func checkIsDueAfterSixHours() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    #expect(updateCheckDue(last: nil, now: now))
    #expect(!updateCheckDue(last: now.addingTimeInterval(-(5 * 3600 + 59 * 60)), now: now))
    #expect(updateCheckDue(last: now.addingTimeInterval(-6 * 3600), now: now))
}

@Test func noSwapFromTheDmgOrTranslocation() {
    #expect(!canSwapInPlace(bundlePath: "/Volumes/Minimalistic Radio/Minimalistic Radio.app", writable: true))
    #expect(!canSwapInPlace(bundlePath: "/private/var/folders/x/AppTranslocation/ABC/d/Minimalistic Radio.app", writable: true))
    #expect(canSwapInPlace(bundlePath: "/Applications/Minimalistic Radio.app", writable: true))
    #expect(!canSwapInPlace(bundlePath: "/Applications/Minimalistic Radio.app", writable: false))
}

@Test func failedCheckKeepsTheArrowState() {
    let update = newestUpdate(releases: releases, current: ReleaseTag("macos-v0.9.0")!)!
    #expect(afterCheck(nil, fetchFailed: true, previous: .available(update)) == .available(update))
    #expect(afterCheck(nil, fetchFailed: true, previous: .none) == .none)
    #expect(afterCheck(update, fetchFailed: false, previous: .none) == .available(update))
    #expect(afterCheck(nil, fetchFailed: false, previous: .available(update)) == .none)
    #expect(afterCheck(nil, fetchFailed: false, previous: .downloading(40)) == .downloading(40))
}

// Final review: one failure must not switch a Mac to DMG updates for good, a signature mismatch must not end in
// "install this", and the relaunch must wait for the old process.

@Test func updateFailuresChooseTheirFallback() {
    #expect(updateFallback(for: .network) == .retryLater)
    #expect(updateFallback(for: .permissionDenied) == .downloadDMG)
    #expect(updateFallback(for: .unpackFailed) == .downloadDMG)
    #expect(updateFallback(for: .signatureMismatch) == .openReleasePage)
    #expect(updateFallback(for: .wrongVersion) == .openReleasePage)
    #expect(updateFallback(for: .unverified) == .openReleasePage)
}

@Test func anUnverifiedDiskImageSaysSo() {
    #expect(updateFailureReason(.unverified) == "This update couldn't be verified. Download it from its release page, which opens now.")
}

// MARK: - Links from the GitHub API

@Test(arguments: [
    "https://github.com/zal3wa/minimalistic-radio/releases/tag/macos-v1.0.0",
    "https://github.com/zal3wa/minimalistic-radio/releases/download/macos-v1.0.0/Minimalistic-Radio.dmg",
    "https://GitHub.com/zal3wa/minimalistic-radio/releases/tag/macos-v1.0.0-beta.4",
])
func projectLinksAreUsed(link: String) {
    #expect(projectLink(link)?.absoluteString == link)
}

@Test(arguments: [
    "http://github.com/zal3wa/minimalistic-radio/releases/tag/macos-v1.0.0",          // not https
    "https://evil.example/zal3wa/minimalistic-radio/releases/tag/macos-v1.0.0",       // not GitHub
    "https://github.com.evil.example/zal3wa/minimalistic-radio/releases/tag/x",
    "https://evilgithub.com/zal3wa/minimalistic-radio/releases/tag/x",
    "https://api.github.com/zal3wa/minimalistic-radio/releases/tag/x",
    "https://github.com/someone/minimalistic-radio/releases/tag/macos-v1.0.0",        // another project
    "https://github.com/zal3wa/minimalistic-radio-fork/releases/tag/x",
    "https://github.com/zal3wa/minimalistic-radio",                                   // not under the project
    "https://github.com/zal3wa/minimalistic-radio/../evil/releases/tag/x",
    "https://github.com/zal3wa/minimalistic-radio/%2E%2E/evil/releases/tag/x",
    "https://user@github.com/zal3wa/minimalistic-radio/releases/tag/x",
    "https://github.com:8443/zal3wa/minimalistic-radio/releases/tag/x",
    "javascript:alert(1)",
    "",
])
func otherLinksAreNotUsed(link: String) {
    #expect(projectLink(link) == nil)
}

@Test func anUntrustedReleasePageFallsBackToTheProjectPage() {
    var odd = release("macos-v2.0.0")
    odd["html_url"] = "https://evil.example/download-me"
    #expect(newestUpdate(releases: [odd], current: ReleaseTag("macos-v1.0.0")!)?.page == projectReleasesPage)
    odd["html_url"] = nil
    #expect(newestUpdate(releases: [odd], current: ReleaseTag("macos-v1.0.0")!)?.page == projectReleasesPage)
    #expect(projectReleasesPage.absoluteString == "https://github.com/zal3wa/minimalistic-radio/releases")
}

@Test func untrustedDownloadsSkipTheRelease() {
    let elsewhere: [String: Any] = ["name": "Minimalistic-Radio.dmg", "browser_download_url": "https://evil.example/Minimalistic-Radio.dmg"]
    var dmg = release("macos-v2.0.0")
    dmg["assets"] = [elsewhere, asset("macos-v2.0.0", "Minimalistic-Radio-macOS.zip")]
    #expect(newestUpdate(releases: [dmg, release("macos-v1.5.0")], current: ReleaseTag("macos-v1.0.0")!)?.tagName == "macos-v1.5.0")
    var zip = release("macos-v2.0.0")
    zip["assets"] = [asset("macos-v2.0.0", "Minimalistic-Radio.dmg"),
                     ["name": "Minimalistic-Radio-macOS.zip", "browser_download_url": "http://github.com/zal3wa/minimalistic-radio/releases/download/macos-v2.0.0/Minimalistic-Radio-macOS.zip"]]
    #expect(newestUpdate(releases: [zip], current: ReleaseTag("macos-v1.0.0")!) == nil)
}

@Test func everyUpdateFailureIsExplained() {
    let reasons = UpdateError.allCases.map(updateFailureReason)
    #expect(reasons.allSatisfy { !$0.isEmpty })
    #expect(Set(reasons).count == UpdateError.allCases.count)
}

@Test func relaunchWaitsForTheOldProcess() {
    let command = relaunchCommand(processID: 4321, resume: true)
    #expect(command.contains("kill -0 4321"))
    #expect(command.hasSuffix("--args --resume"))
    #expect(!relaunchCommand(processID: 1, resume: false).contains("--resume"))
}
