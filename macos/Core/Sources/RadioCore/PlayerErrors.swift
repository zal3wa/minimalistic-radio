/// How a playback problem is handled (linux/minimalistic_radio/controller.py ErrorKind).
public enum ErrorKind: Sendable {
    /// The connection failed or dropped: retried.
    case network
    /// The station said no: stops at once.
    case refused
    /// A format the player can't decode: stops at once.
    case unsupported
}

/// AVFoundation's and URLSession's errors, sorted the way the controller needs them.
public func classify(domain: String, code: Int, httpStatus: Int?) -> ErrorKind {
    if let httpStatus, [401, 403, 404, 410].contains(httpStatus) { return .refused }
    // AVError.fileFormatNotRecognized (-11828) and .decoderNotFound (-11833).
    if domain == "AVFoundationErrorDomain" && (code == -11828 || code == -11833) { return .unsupported }
    return .network
}
