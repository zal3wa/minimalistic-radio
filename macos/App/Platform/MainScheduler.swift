import Foundation
import RadioCore

/// The controller's timers, on the main queue.
final class MainScheduler: Scheduler {
    func callLater(_ seconds: Double, _ block: @escaping () -> Void) -> AnyObject {
        let work = DispatchWorkItem(block: block)
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: work)
        return work
    }

    func cancel(_ handle: AnyObject) {
        (handle as? DispatchWorkItem)?.cancel()
    }

    func now() -> Date {
        Date()
    }
}
