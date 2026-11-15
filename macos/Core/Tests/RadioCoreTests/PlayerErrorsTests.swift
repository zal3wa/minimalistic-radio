import Testing
@testable import RadioCore

@Test func errorsAreClassified() {
    #expect(classify(domain: "NSURLErrorDomain", code: -1009, httpStatus: nil) == .network)
    #expect(classify(domain: "NSURLErrorDomain", code: -1011, httpStatus: 403) == .refused)
    #expect(classify(domain: "CoreMediaErrorDomain", code: -12938, httpStatus: 404) == .refused)
    #expect(classify(domain: "AVFoundationErrorDomain", code: -11828, httpStatus: nil) == .unsupported)
    #expect(classify(domain: "AVFoundationErrorDomain", code: -11833, httpStatus: nil) == .unsupported)
    #expect(classify(domain: "AVFoundationErrorDomain", code: -11800, httpStatus: nil) == .network)
    #expect(classify(domain: "NSURLErrorDomain", code: -1001, httpStatus: 500) == .network)
}
