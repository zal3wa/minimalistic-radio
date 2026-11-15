import AppKit
import RadioCore
import Security

/// Self-updates, as on Windows: a check every 6 hours, a green arrow and an "Update" menu item when a newer Mac
/// release is out, and one click to download it, check its signature, swap the app and restart.
/// Only in releases (the build's MRReleaseTag is a macos-v tag); development builds never check.
@MainActor
final class Updater {
    private let controller: RadioController
    private let current: ReleaseTag?
    private var timer: Timer?
    private static let explainedKey = "UpdatePermissionExplained"

    private(set) var state: UpdateState = .none {
        didSet { if state != oldValue { onChange() } }
    }
    var onChange: () -> Void = {}
    var showCard: (String) -> Void = { _ in }

    init(controller: RadioController) {
        self.controller = controller
        current = ReleaseTag(Bundle.main.object(forInfoDictionaryKey: "MRReleaseTag") as? String ?? "")
    }

    var enabled: Bool { current != nil }

    /// The menu item's and the arrow's label while an update is ready.
    var label: String? {
        guard case .available = state else { return nil }
        return controller.prefs.updateByDownload ? L("Download update") : L("Update")
    }

    func start() {
        guard enabled else { return }
        checkIfDue()
        timer = Timer.scheduledTimer(withTimeInterval: 3600, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.checkIfDue() }
        }
    }

    func checkIfDue() {
        guard enabled, controller.prefs.checkUpdates,
              updateCheckDue(last: controller.prefs.lastUpdateCheck, now: Date()) else { return }
        check { _ in }
    }

    /// Settings → Check now: the result as a sentence.
    func checkNow(_ done: @escaping (String) -> Void) {
        guard enabled else { return done(L("You have the latest version.")) }
        check { failed in
            if failed {
                done(L("Couldn't check for updates."))
            } else if case .available(let update) = self.state {
                done(update.tagName.replacingOccurrences(of: "macos-v", with: ""))
            } else {
                done(L("You have the latest version."))
            }
        }
    }

    private func check(_ done: @escaping (Bool) -> Void) {
        Network.fetchJSON(releasesURL) { [weak self] payload in
            guard let self else { return }
            let failed = payload == nil
            let update = self.current.flatMap { newestUpdate(releases: payload, current: $0) }
            if !failed { self.controller.setLastUpdateCheck(Date()) }
            self.state = afterCheck(update, fetchFailed: failed, previous: self.state)
            done(failed)
        }
    }

    // MARK: - Installing

    func install() {
        guard case .available(let update) = state else { return }
        let bundle = Bundle.main.bundleURL
        let writable = FileManager.default.isWritableFile(atPath: bundle.deletingLastPathComponent().path)
        if controller.prefs.updateByDownload || !canSwapInPlace(bundlePath: bundle.path, writable: writable) {
            downloadDMG(update)
            return
        }
        if !UserDefaults.standard.bool(forKey: Self.explainedKey) {
            UserDefaults.standard.set(true, forKey: Self.explainedKey)
            showCard(L("macOS may ask once for permission to update the radio."))
        }
        state = .downloading(0)
        Task {
            do {
                let app = try await Self.downloadApp(update.zip)
                guard Self.signedLikeThisApp(app) else { throw UpdateFailure() }
                _ = try FileManager.default.replaceItemAt(bundle, withItemAt: app)
                relaunch(bundle)
            } catch {
                downloadDMG(update)
            }
        }
    }

    struct UpdateFailure: Error {}

    /// The release's zip, unpacked: the new Minimalistic Radio.app in a temporary folder.
    private static func downloadApp(_ zip: URL) async throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("radio-update-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let (file, response) = try await Network.session.download(from: zip)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateFailure() }
        let archive = folder.appendingPathComponent("update.zip")
        try FileManager.default.moveItem(at: file, to: archive)
        let unzip = Process()
        unzip.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        unzip.arguments = ["-x", "-k", archive.path, folder.path]
        try unzip.run()
        unzip.waitUntilExit()
        let app = folder.appendingPathComponent("Minimalistic Radio.app")
        guard unzip.terminationStatus == 0, FileManager.default.fileExists(atPath: app.path) else { throw UpdateFailure() }
        return app
    }

    /// The new app meets this app's designated requirement: signed with the same project certificate.
    private static func signedLikeThisApp(_ app: URL) -> Bool {
        var running: SecCode?
        var runningStatic: SecStaticCode?
        var requirement: SecRequirement?
        var candidate: SecStaticCode?
        guard SecCodeCopySelf([], &running) == errSecSuccess, let running,
              SecCodeCopyStaticCode(running, [], &runningStatic) == errSecSuccess, let runningStatic,
              SecCodeCopyDesignatedRequirement(runningStatic, [], &requirement) == errSecSuccess, let requirement,
              SecStaticCodeCreateWithPath(app as CFURL, [], &candidate) == errSecSuccess, let candidate else { return false }
        let flags = SecCSFlags(rawValue: kSecCSCheckAllArchitectures | kSecCSStrictValidate)
        return SecStaticCodeCheckValidity(candidate, flags, requirement) == errSecSuccess
    }

    /// Starts the new version once this one has quit, playing the same station if it was playing.
    private func relaunch(_ bundle: URL) {
        let restart = Process()
        restart.executableURL = URL(fileURLWithPath: "/bin/sh")
        var command = "sleep 1; /usr/bin/open \"$0\""
        if controller.active { command += " --args --resume" }
        restart.arguments = ["-c", command, bundle.path]
        try? restart.run()
        NSApp.terminate(nil)
    }

    /// When the app can't replace itself (opened from the DMG or Downloads, or macOS said no): the DMG opens in
    /// Finder, to drag the radio to Applications. From then on this Mac gets "Download update".
    private func downloadDMG(_ update: AvailableUpdate) {
        state = .downloading(0)
        Task {
            do {
                let (file, response) = try await Network.session.download(from: update.dmg)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateFailure() }
                let target = FileManager.default.temporaryDirectory.appendingPathComponent("Minimalistic-Radio-\(UUID().uuidString).dmg")
                try FileManager.default.moveItem(at: file, to: target)
                controller.setUpdateByDownload(true)
                NSWorkspace.shared.open(target)
                showCard(L("Drag Minimalistic Radio to Applications to finish the update."))
                state = .available(update)
            } catch {
                NSWorkspace.shared.open(update.page)
                state = .available(update)
            }
        }
    }
}
