import Foundation

/// A new empty folder for one test.
func tempFolder() -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("radio-tests-" + UUID().uuidString)
    try! FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

/// A local date and time, whole seconds (as the files store them).
func localDate(_ year: Int, _ month: Int, _ day: Int, _ hour: Int, _ minute: Int, _ second: Int = 0) -> Date {
    var parts = DateComponents()
    (parts.year, parts.month, parts.day, parts.hour, parts.minute, parts.second) = (year, month, day, hour, minute, second)
    return Calendar.current.date(from: parts)!
}
