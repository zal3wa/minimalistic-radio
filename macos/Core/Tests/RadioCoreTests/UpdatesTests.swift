import Foundation
import Testing
@testable import RadioCore

private func release(_ tag: String, draft: Bool = false, zip: Bool = true) -> [String: Any] {
    var assets: [[String: Any]] = [["name": "Minimalistic-Radio.dmg", "browser_download_url": "https://github.com/x/\(tag)/Minimalistic-Radio.dmg"]]
    if zip { assets.append(["name": "Minimalistic-Radio-macOS.zip", "browser_download_url": "https://github.com/x/\(tag)/Minimalistic-Radio-macOS.zip"]) }
    return ["tag_name": tag, "draft": draft, "html_url": "https://github.com/x/releases/tag/\(tag)", "assets": assets]
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
    #expect(update?.zip.absoluteString == "https://github.com/x/macos-v1.0.0/Minimalistic-Radio-macOS.zip")
    #expect(update?.dmg.absoluteString == "https://github.com/x/macos-v1.0.0/Minimalistic-Radio.dmg")
    #expect(update?.page.absoluteString == "https://github.com/x/releases/tag/macos-v1.0.0")
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
