import Foundation

// One cleanup for names and song titles from outside, the same on Windows, Linux and the Mac
// (docs/superpowers/specs/2026-11-16-security-hardening-design.md, "Names"): share links, radio-browser, the
// station form, import and stations.json all go through cleanName; song titles through withoutHiddenCharacters.

let nameLimit = 100

/// The bidirectional formatting characters, which can make a name read differently from what it is.
private let bidiFormatting: Set<UInt32> = [0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                                           0x2066, 0x2067, 0x2068, 0x2069]

/// Without control characters (Unicode Cc) and bidirectional formatting characters. Zero-width joiners and
/// variation selectors stay, so emoji still work.
public func withoutHiddenCharacters(_ text: String) -> String {
    var kept = String.UnicodeScalarView()
    kept.append(contentsOf: text.unicodeScalars.filter {
        $0.properties.generalCategory != .control && !bidiFormatting.contains($0.value)
    })
    return String(kept)
}

/// A station name as the radio keeps it: cleaned, trimmed and at most 100 characters; empty when nothing is left.
public func cleanName(_ name: String?) -> String {
    let text = withoutHiddenCharacters(name ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    return String(text.prefix(nameLimit)).trimmingCharacters(in: .whitespacesAndNewlines)
}
