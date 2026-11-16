import CoreGraphics
import Foundation

// Temporary: only the declarations the new security tests need, doing nothing yet, so the tests compile and fail
// first. Each one is replaced by its real code in the commits that follow.

public typealias ResolveHost = (String) -> [String]?
public func pictureAddressAllowed(_ url: URL, resolve: ResolveHost) -> Bool { true }
public func systemResolve(_ host: String) -> [String]? { nil }
public func redirectTarget(_ location: String?, from: URL) -> URL? { nil }
public enum PictureAnswer { case redirect(String?), data(Data) }
public struct PictureRefused: Error {}
public func followPictureRedirects(_ url: URL, allowed: (URL) async -> Bool,
                                   get: (URL) async throws -> PictureAnswer) async throws -> Data { Data() }

public func pictureSizeAllowed(width: Int, height: Int) -> Bool { true }
public func declaredPictureSize(_ data: Data) -> (width: Int, height: Int)? { nil }
public func decodePicture(_ data: Data, maxPixels: Int) -> CGImage? { nil }
