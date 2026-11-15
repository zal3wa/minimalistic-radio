import Foundation

/// The app's version ("1.0.0"), or "0.0.0" outside the radio's own bundle (tests, tools).
public var appVersion: String {
    guard Bundle.main.bundleIdentifier == "io.github.zal3wa.minimalistic-radio" else { return "0.0.0" }
    return Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.0.0"
}
