import AppKit
import os
import RadioCore
import Security

/// Self-updates, as on Windows: a check every 6 hours, a green arrow and an "Update" menu item when a newer Mac
/// release is out, and one click to download it, check its signature and version, swap the app and restart.
/// Only in releases (the build's MRReleaseTag is a macos-v tag); development builds never check.
@MainActor
final class Updater {
    private let controller: RadioController
    private let current: ReleaseTag?
    private var timer: Timer?
    private static let explainedKey = "UpdatePermissionExplained"
    nonisolated private static let log = Logger(subsystem: "io.github.zal3wa.minimalistic-radio", category: "updates")
    /// Temporary folders of update downloads (the zip, the disk image and its hidden mount point).
    nonisolated private static let folderPrefix = "radio-update-"

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

    /// The app can replace itself where it is (not from the DMG, Downloads or a folder it can't write).
    private var canSwapHere: Bool {
        let bundle = Bundle.main.bundleURL
        let writable = FileManager.default.isWritableFile(atPath: bundle.deletingLastPathComponent().path)
        return canSwapInPlace(bundlePath: bundle.path, writable: writable)
    }

    /// The menu item's and the arrow's label while an update is ready.
    var label: String? {
        guard case .available = state else { return nil }
        return canSwapHere ? L("Update") : L("Download update")
    }

    func start() {
        // Beta 1 remembered a DMG fallback for good; now each update decides for itself.
        if controller.prefs.updateByDownload { controller.setUpdateByDownload(false) }
        guard enabled else { return }
        let started = Date()
        Task.detached(priority: .background) { Self.removeOldDownloads(before: started) }
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
                done(L("Update to {0}").replacingOccurrences(of: "{0}", with: update.tagName.replacingOccurrences(of: "macos-v", with: "")))
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
        guard canSwapHere else {
            downloadDMG(update)
            return
        }
        if !UserDefaults.standard.bool(forKey: Self.explainedKey) {
            UserDefaults.standard.set(true, forKey: Self.explainedKey)
            showCard(L("macOS may ask once for permission to update the radio."))
        }
        state = .downloading(0)
        let bundle = Bundle.main.bundleURL
        Task {
            do {
                let app = try await Self.downloadApp(update.zip)
                guard Self.signedLikeThisApp(app) else { throw UpdateError.signatureMismatch }
                guard Bundle(url: app)?.object(forInfoDictionaryKey: "MRReleaseTag") as? String == update.tagName else {
                    throw UpdateError.wrongVersion
                }
                do {
                    _ = try FileManager.default.replaceItemAt(bundle, withItemAt: app)
                } catch {
                    Self.log.error("replacing the app failed: \(String(describing: error), privacy: .public)")
                    throw UpdateError.permissionDenied
                }
                relaunch(bundle)
            } catch let error as UpdateError {
                failed(update, error)
            } catch {
                Self.log.error("downloading the update failed: \(String(describing: error), privacy: .public)")
                failed(update, .network)
            }
        }
    }

    /// Says why on the card, and takes the fallback that fits: try later, the DMG, or the release page.
    private func failed(_ update: AvailableUpdate, _ error: UpdateError) {
        Self.log.error("update \(update.tagName, privacy: .public) failed: \(String(describing: error), privacy: .public)")
        showCard(L(updateFailureReason(error)))
        switch updateFallback(for: error) {
        case .retryLater:
            state = .available(update)
        case .downloadDMG:
            downloadDMG(update)
        case .openReleasePage:
            NSWorkspace.shared.open(update.page)
            state = .available(update)
        }
    }

    /// The release's zip, unpacked: the new Minimalistic Radio.app in a temporary folder.
    private static func downloadApp(_ zip: URL) async throws -> URL {
        let folder = newFolder()
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let (file, response) = try await Network.session.download(from: zip)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateError.network }
        let archive = folder.appendingPathComponent("update.zip")
        try FileManager.default.moveItem(at: file, to: archive)
        let unzip = Process()
        unzip.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        unzip.arguments = ["-x", "-k", archive.path, folder.path]
        do {
            try unzip.run()
        } catch {
            throw UpdateError.unpackFailed
        }
        unzip.waitUntilExit()
        let app = folder.appendingPathComponent("Minimalistic Radio.app")
        guard unzip.terminationStatus == 0, FileManager.default.fileExists(atPath: app.path) else { throw UpdateError.unpackFailed }
        return app
    }

    /// The new app meets this app's designated requirement: signed with the same project certificate.
    nonisolated private static func signedLikeThisApp(_ app: URL) -> Bool {
        signatureStatus(app) == errSecSuccess
    }

    /// errSecSuccess when `app` meets this app's designated requirement, else the first error on the way.
    nonisolated private static func signatureStatus(_ app: URL) -> OSStatus {
        var running: SecCode?
        var runningStatic: SecStaticCode?
        var requirement: SecRequirement?
        var candidate: SecStaticCode?
        var status = SecCodeCopySelf([], &running)
        if status == errSecSuccess, let running { status = SecCodeCopyStaticCode(running, [], &runningStatic) }
        if status == errSecSuccess, let runningStatic { status = SecCodeCopyDesignatedRequirement(runningStatic, [], &requirement) }
        if status == errSecSuccess { status = SecStaticCodeCreateWithPath(app as CFURL, [], &candidate) }
        guard status == errSecSuccess, let requirement, let candidate else {
            log.error("the update's signature couldn't be checked: \(status)")
            return status == errSecSuccess ? errSecInternalComponent : status
        }
        let flags = SecCSFlags(rawValue: kSecCSCheckAllArchitectures | kSecCSStrictValidate)
        status = SecStaticCodeCheckValidity(candidate, flags, requirement)
        if status != errSecSuccess { log.error("the update's signature check returned \(status)") }
        return status
    }

    /// Starts the new version once this process has quit, playing the same station if it was playing.
    private func relaunch(_ bundle: URL) {
        let restart = Process()
        restart.executableURL = URL(fileURLWithPath: "/bin/sh")
        restart.arguments = ["-c", relaunchCommand(processID: ProcessInfo.processInfo.processIdentifier, resume: controller.active),
                             bundle.path]
        try? restart.run()
        NSApp.terminate(nil)
    }

    /// When the app can't replace itself (opened from the DMG or Downloads, or macOS said no): the DMG is checked
    /// like a zip update, then opens in Finder, to drag the radio to Applications. Only for this update; the next
    /// one tries the swap again. A DMG that fails the check is never shown: its release page opens instead.
    private func downloadDMG(_ update: AvailableUpdate) {
        state = .downloading(0)
        Task {
            let dmg = Self.newFolder().appendingPathComponent(updateDMGName)
            do {
                try FileManager.default.createDirectory(at: dmg.deletingLastPathComponent(), withIntermediateDirectories: true)
                let (file, response) = try await Network.session.download(from: update.dmg)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateError.network }
                try FileManager.default.moveItem(at: file, to: dmg)
            } catch {
                Self.log.error("downloading the DMG failed: \(String(describing: error), privacy: .public)")
                try? FileManager.default.removeItem(at: dmg.deletingLastPathComponent())
                NSWorkspace.shared.open(update.page)
                state = .available(update)
                return
            }
            let tag = update.tagName
            let checked = await Task.detached(priority: .userInitiated) { Self.mountVerifiedDMG(dmg, tag: tag) }.value
            guard let volume = checked else {
                try? FileManager.default.removeItem(at: dmg.deletingLastPathComponent())
                failed(update, .unverified)
                return
            }
            if !NSWorkspace.shared.open(volume) {
                // Finder didn't show the hidden volume: the same image, already checked, mounted the usual way.
                Self.detach(volume)
                NSWorkspace.shared.open(dmg)
            }
            showCard(L("Quit the radio, then drag Minimalistic Radio to Applications to finish the update."))
            state = .available(update)
        }
    }

    // MARK: - Checking a disk image

    nonisolated private static func newFolder() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent(folderPrefix + UUID().uuidString)
    }

    /// Mounts the DMG read-only and hidden at a private mount point, and checks the app inside as a zip update is
    /// checked: signed like this app, with the release's tag. Returns the mount point when it passes. Otherwise
    /// the DMG is detached and deleted, `report` gets the reason, and nil comes back.
    nonisolated static func mountVerifiedDMG(_ dmg: URL, tag: String, report: (String) -> Void = { _ in }) -> URL? {
        let folder = newFolder()
        let volume = folder.appendingPathComponent("volume")
        let reason: String
        let attach: (ok: Bool, output: String)
        do {
            try FileManager.default.createDirectory(at: volume, withIntermediateDirectories: true)
            attach = run("/usr/bin/hdiutil", ["attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", volume.path,
                                              dmg.path])
        } catch {
            attach = (false, String(describing: error))
        }
        let app = volume.appendingPathComponent("Minimalistic Radio.app")
        let values = try? app.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        if !attach.ok {
            reason = "the disk image didn't mount"
            report("hdiutil: " + attach.output)   // only for --check-update-dmg: never logged
        } else if values?.isDirectory != true || values?.isSymbolicLink == true {
            reason = "the disk image has no Minimalistic Radio.app"
        } else if case let status = signatureStatus(app), status != errSecSuccess {
            reason = "the app isn't signed like this one (\(status))"
        } else if case let found = Bundle(url: app)?.object(forInfoDictionaryKey: "MRReleaseTag") as? String, found != tag {
            reason = "the app's release tag is \(found ?? "missing"), not \(tag)"
        } else {
            return volume
        }
        log.error("the update's disk image failed its check: \(reason, privacy: .public)")
        report(reason)
        if attach.ok { detach(volume) }
        try? FileManager.default.removeItem(at: dmg)
        if !isMountPoint(volume) { try? FileManager.default.removeItem(at: folder) }
        return nil
    }

    /// Unmounts a checked disk image (forcibly if it is busy) and removes its mount point.
    nonisolated static func detach(_ volume: URL) {
        if !run("/usr/bin/hdiutil", ["detach", volume.path]).ok { _ = run("/usr/bin/hdiutil", ["detach", "-force", volume.path]) }
        if !isMountPoint(volume) { try? FileManager.default.removeItem(at: volume.deletingLastPathComponent()) }
    }

    /// `--check-update-dmg <dmg> <tag>` (CI): the disk-image check alone. Exit code 0 when the DMG passes (it is
    /// detached again), 1 when it fails (it is detached and deleted, and the reason goes to standard error).
    nonisolated static func checkDMG(_ dmg: URL, tag: String) -> Int32 {
        let report = { (reason: String) in FileHandle.standardError.write(Data("update DMG check: \(reason)\n".utf8)) }
        guard let volume = mountVerifiedDMG(dmg, tag: tag, report: report) else { return 1 }
        detach(volume)
        return 0
    }

    /// Update downloads from before `date`, unpacked zips and checked disk images still mounted (once the radio was
    /// dragged to Applications): detached and removed, except the one this copy runs from.
    nonisolated private static func removeOldDownloads(before date: Date) {
        let files = FileManager.default
        let running = Bundle.main.bundleURL.resolvingSymlinksInPath().path
        guard let folders = try? files.contentsOfDirectory(at: files.temporaryDirectory,
                                                           includingPropertiesForKeys: [.creationDateKey]) else { return }
        for folder in folders where folder.lastPathComponent.hasPrefix(folderPrefix) {
            let created = (try? folder.resourceValues(forKeys: [.creationDateKey]))?.creationDate ?? .distantFuture
            if created >= date || running.hasPrefix(folder.resolvingSymlinksInPath().path + "/") { continue }
            let volume = folder.appendingPathComponent("volume")
            if isMountPoint(volume) && !run("/usr/bin/hdiutil", ["detach", volume.path]).ok { continue }
            try? files.removeItem(at: folder)
        }
    }

    /// Something is mounted at `path` (it is on another device than its folder).
    nonisolated private static func isMountPoint(_ path: URL) -> Bool {
        var inner = stat(), outer = stat()
        guard stat(path.path, &inner) == 0, stat(path.deletingLastPathComponent().path, &outer) == 0 else { return false }
        return inner.st_dev != outer.st_dev
    }

    /// Runs a tool with no input; whether it worked, and what it wrote.
    nonisolated private static func run(_ tool: String, _ arguments: [String]) -> (ok: Bool, output: String) {
        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: tool)
        process.arguments = arguments
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = output
        process.standardError = output
        do {
            try process.run()
        } catch {
            return (false, String(describing: error))
        }
        let written = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return (process.terminationStatus == 0, String(decoding: written, as: UTF8.self))
    }
}
