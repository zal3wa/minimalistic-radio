from minimalistic_radio.i18n import install, languages_for


def test_a_chosen_language_ignores_the_system():
    assert languages_for("pl", ["en_US"]) == ["pl"]
    assert languages_for("en", ["pl_PL"]) == ["en"]


def test_auto_follows_the_system():
    assert languages_for("auto", ["pl_PL", "en"]) == ["pl"]


def test_english_without_a_translation_file(tmp_path):
    assert install("en", str(tmp_path / "missing"))("Play") == "Play"


def test_auto_language_picks_first_supported():
    assert languages_for("auto", ["uk_UA", "en"]) == ["uk"]
    assert languages_for("auto", ["ru_RU", "de_DE"]) == ["de"]
    assert languages_for("auto", ["ru_RU"]) == ["en"]


def _catalog(path):
    import ast
    entries, key, field = {}, None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("msgid "):
            key, field = ast.literal_eval(line[6:]), "id"
            entries[key] = ""
        elif line.startswith("msgstr "):
            field = "str"
            entries[key] = ast.literal_eval(line[7:])
        elif line.startswith('"') and key is not None:
            if field == "id":
                del entries[key]
                key += ast.literal_eval(line)
                entries[key] = ""
            else:
                entries[key] += ast.literal_eval(line)
    return entries


def test_every_catalog_complete():
    from pathlib import Path
    folder = Path(__file__).resolve().parents[2] / "po"
    english = {k for k in _catalog(folder / "pl.po") if k}
    missing = {}
    for code in (folder / "LINGUAS").read_text().split():
        catalog = _catalog(folder / f"{code}.po")
        gaps = sorted(k for k in english if not catalog.get(k))
        extra = sorted(k for k in catalog if k and k not in english)
        if gaps or extra:
            missing[code] = (gaps, extra)
    assert not missing
