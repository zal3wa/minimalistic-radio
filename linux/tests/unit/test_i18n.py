from minimalistic_radio.i18n import install, languages_for


def test_a_chosen_language_ignores_the_system():
    assert languages_for("pl", ["en_US"]) == ["pl"]
    assert languages_for("en", ["pl_PL"]) == ["en"]


def test_auto_follows_the_system():
    assert languages_for("auto", ["pl_PL", "en"]) == ["pl_PL", "en"]


def test_english_without_a_translation_file(tmp_path):
    assert install("en", str(tmp_path / "missing"))("Play") == "Play"
