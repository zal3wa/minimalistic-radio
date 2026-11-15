import Testing
@testable import RadioCore

@Test func versionFallsBackOutsideAnApp() {
    #expect(appVersion == "0.0.0")
}
