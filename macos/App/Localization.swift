import Foundation
import RadioCore

/// The UI's texts: English in the code, translated from the bundled Lang/<code>.po catalogues.
/// The language comes from Settings ("auto" follows macOS) and switches at once, as on Windows.
let localizer: Localizer = {
    var catalogs: [String: Catalog] = [:]
    for code in supportedLanguages where code != "en" {
        if let url = Bundle.main.url(forResource: code, withExtension: "po", subdirectory: "Lang"),
           let text = try? String(contentsOf: url, encoding: .utf8) {
            catalogs[code] = Catalog(po: text)
        }
    }
    return Localizer(catalogs: catalogs, system: Locale.preferredLanguages)
}()

/// `english` in the UI's language.
func L(_ english: String) -> String {
    localizer.text(english)
}
