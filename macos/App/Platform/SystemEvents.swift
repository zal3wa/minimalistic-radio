import AppKit
import Network
import RadioCore

/// Back after sleep and network changes: the old connection is dead, so the controller connects again
/// (if it was playing, or gave up on a lost connection less than 10 minutes earlier). Going to sleep ends the
/// listening session for the statistics, so the time asleep doesn't count.
@MainActor
final class SystemEvents {
    private let controller: RadioController
    private let monitor = NWPathMonitor()
    private var networkWasDown = false
    private var wake: NSObjectProtocol?
    private var sleep: NSObjectProtocol?

    init(controller: RadioController) {
        self.controller = controller
        wake = NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.didWakeNotification, object: nil,
                                                                 queue: .main) { [weak self] _ in
            self?.controller.resumed()
        }
        sleep = NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.willSleepNotification, object: nil,
                                                                  queue: .main) { [weak self] _ in
            self?.controller.willSleep()
        }
        monitor.pathUpdateHandler = { [weak self] path in
            let satisfied = path.status == .satisfied
            DispatchQueue.main.async { self?.networkChanged(satisfied) }
        }
        monitor.start(queue: DispatchQueue(label: "network monitor"))
    }

    private func networkChanged(_ satisfied: Bool) {
        if !satisfied {
            networkWasDown = true
        } else if networkWasDown {
            networkWasDown = false
            controller.networkAvailable(wasDown: true)
        }
    }
}
