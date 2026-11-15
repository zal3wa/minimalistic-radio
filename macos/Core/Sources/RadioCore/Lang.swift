import Foundation

// The radio's languages: English texts in the code, translated from gettext .po catalogues (macos/Lang/*.po),
// switched live like the Windows app. `languagesFor` is a port of linux/minimalistic_radio/i18n.py.

public let supportedLanguages = ["pl", "en", "de", "uk", "cs", "es", "fr", "it", "pt"]

/// [the language to use]: the chosen one, or for "auto" the first supported language of `system`
/// (["uk_UA", "en"] or ["uk-UA", "en"] gives ["uk"]), else English.
public func languagesFor(setting: String, system: [String]) -> [String] {
    if supportedLanguages.contains(setting) { return [setting] }
    for entry in system {
        let code = String(entry.split(whereSeparator: { "_.@-".contains($0) }).first ?? "").lowercased()
        if supportedLanguages.contains(code) { return [code] }
    }
    return ["en"]
}

/// One .po catalogue: msgid → msgstr. The header and untranslated entries are left out.
public struct Catalog: Sendable {
    private var entries: [String: String] = [:]

    public init(po: String) {
        var id: String?
        var text = ""
        var field = ""
        func finish() {
            if let id, !id.isEmpty, !text.isEmpty { entries[id] = text }
        }
        for rawLine in po.components(separatedBy: .newlines) {
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("msgid ") {
                finish()
                id = Catalog.unquote(String(line.dropFirst(6)))
                text = ""
                field = "id"
            } else if line.hasPrefix("msgstr ") {
                text = Catalog.unquote(String(line.dropFirst(7)))
                field = "str"
            } else if line.hasPrefix("\"") {
                if field == "id" { id = (id ?? "") + Catalog.unquote(line) } else if field == "str" { text += Catalog.unquote(line) }
            } else if line.hasPrefix("msgid_plural") || line.hasPrefix("msgstr[") {
                field = ""   // plural forms aren't used by the Mac app
            }
        }
        finish()
    }

    public func translate(_ text: String) -> String? {
        entries[text]
    }

    /// "\"A \\\"b\\\"\\n\"" → "A \"b\"\n".
    static func unquote(_ quoted: String) -> String {
        var body = Substring(quoted.trimmingCharacters(in: .whitespaces))
        if body.hasPrefix("\"") { body = body.dropFirst() }
        if body.hasSuffix("\"") { body = body.dropLast() }
        var result = ""
        var escaped = false
        for character in body {
            if escaped {
                switch character {
                case "n": result.append("\n")
                case "t": result.append("\t")
                default: result.append(character)
                }
                escaped = false
            } else if character == "\\" {
                escaped = true
            } else {
                result.append(character)
            }
        }
        return result
    }
}

/// The UI's language: `setting` is "auto" or a language code, and changing it changes the next `text` at once.
public final class Localizer {
    public var setting = "auto"
    private let catalogs: [String: Catalog]
    private let system: [String]

    public init(catalogs: [String: Catalog], system: [String]) {
        self.catalogs = catalogs
        self.system = system
    }

    /// The language in use ("pl"), for dates and the directory's country.
    public var language: String {
        languagesFor(setting: setting, system: system)[0]
    }

    public func text(_ english: String) -> String {
        let code = language
        if code == "en" { return english }
        return catalogs[code]?.translate(english) ?? english
    }
}
