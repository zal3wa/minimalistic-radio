import Testing
@testable import RadioCore

// Ported from linux/tests/unit/test_i18n.py (languages_for), plus the Mac's catalogue reader and live switching.

@Test func aChosenLanguageIgnoresTheSystem() {
    #expect(languagesFor(setting: "pl", system: ["en_US"]) == ["pl"])
    #expect(languagesFor(setting: "en", system: ["pl_PL"]) == ["en"])
}

@Test func autoFollowsTheSystem() {
    #expect(languagesFor(setting: "auto", system: ["pl_PL", "en"]) == ["pl"])
    #expect(languagesFor(setting: "auto", system: ["pl-PL", "en-US"]) == ["pl"])   // the Mac's form
}

@Test func autoLanguagePicksFirstSupported() {
    #expect(languagesFor(setting: "auto", system: ["uk_UA", "en"]) == ["uk"])
    #expect(languagesFor(setting: "auto", system: ["ru_RU", "de_DE"]) == ["de"])
    #expect(languagesFor(setting: "auto", system: ["ru_RU"]) == ["en"])
}

@Test func catalogParsesMultilineAndEscapes() {
    let po = "# comment\nmsgid \"\"\nmsgstr \"Language: pl\\n\"\n\nmsgid \"A \\\"b\\\"\\n\"\n\"c\"\nmsgstr \"Ą \\\"b\\\"\\n\"\n\"ć\"\n\nmsgid \"Empty\"\nmsgstr \"\"\n"
    let catalog = Catalog(po: po)
    #expect(catalog.translate("A \"b\"\nc") == "Ą \"b\"\nć")
    #expect(catalog.translate("Empty") == nil)
    #expect(catalog.translate("") == nil)
}

@Test func localizerSwitchesLive() {
    let localizer = Localizer(catalogs: ["pl": Catalog(po: "msgid \"Stop\"\nmsgstr \"Zatrzymaj\"\n"),
                                         "de": Catalog(po: "msgid \"Stop\"\nmsgstr \"Stopp\"\n")],
                              system: ["pl"])
    localizer.setting = "auto"
    #expect(localizer.text("Stop") == "Zatrzymaj")
    localizer.setting = "de"
    #expect(localizer.text("Stop") == "Stopp")
    localizer.setting = "en"
    #expect(localizer.text("Stop") == "Stop")
}

@Test func englishWithoutACatalog() {
    let localizer = Localizer(catalogs: [:], system: ["pl"])
    #expect(localizer.text("Play") == "Play")
}
