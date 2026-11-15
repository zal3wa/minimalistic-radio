// swift-tools-version: 6.0
// The radio's logic without AppKit: a port of the Linux app's tested core (linux/minimalistic_radio).
import PackageDescription

let package = Package(
    name: "RadioCore",
    platforms: [.macOS(.v13)],
    products: [.library(name: "RadioCore", targets: ["RadioCore"])],
    targets: [
        .target(name: "RadioCore"),
        .testTarget(name: "RadioCoreTests", dependencies: ["RadioCore"]),
    ],
    swiftLanguageModes: [.v5]
)
