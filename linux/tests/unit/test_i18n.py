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
    """{msgid (with "context\\x04" before it): [msgstr, or each plural form]}."""
    import ast
    import re
    entries, context, key, field = {}, "", None, None
    text = ""
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        part = re.match(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?) (".*")$', line)
        if part is None and line.startswith('"'):
            text += ast.literal_eval(line)
            continue
        if field == "msgctxt":
            context = text + "\x04"
        elif field == "msgid":
            key = context + text
            entries[key] = []
            context = ""
        elif field is not None and field.startswith("msgstr"):
            entries[key].append(text)
        field, text = (part.group(1), ast.literal_eval(part.group(2))) if part else (None, "")
    return entries


def _plural_forms(path):
    import re
    header = _catalog(path)[""][0]
    return int(re.search(r"nplurals=(\d+)", header).group(1))


def test_every_catalog_complete():
    from pathlib import Path
    folder = Path(__file__).resolve().parents[2] / "po"
    english = _catalog(folder / "pl.po")
    missing = {}
    for code in (folder / "LINGUAS").read_text().split():
        catalog = _catalog(folder / f"{code}.po")
        forms = _plural_forms(folder / f"{code}.po")
        gaps = sorted(k for k in english if k and (not catalog.get(k) or not all(catalog[k])
                                                   or len(catalog[k]) not in (1, forms)))
        extra = sorted(k for k in catalog if k and k not in english)
        if gaps or extra:
            missing[code] = (gaps, extra)
    assert not missing


def test_translations_keep_the_placeholders():
    import re
    from pathlib import Path
    folder = Path(__file__).resolve().parents[2] / "po"
    wrong = []
    for code in (folder / "LINGUAS").read_text().split():
        for key, texts in _catalog(folder / f"{code}.po").items():
            wanted = sorted(set(re.findall(r"\{\w*\}", key.split("\x04")[-1])))
            wrong += [(code, key, text) for text in texts if key and sorted(set(re.findall(r"\{\w*\}", text))) != wanted]
    assert not wrong


def test_the_catalog_reader_knows_contexts_and_plurals(tmp_path):
    po = tmp_path / "x.po"
    po.write_text('msgid ""\nmsgstr ""\n"Plural-Forms: nplurals=3; plural=0;\\n"\n\n'
                  'msgctxt "month"\nmsgid "March"\nmsgstr "marzec"\n\n'
                  'msgid "{n} play"\nmsgid_plural "{n} plays"\nmsgstr[0] "a"\nmsgstr[1] "b"\nmsgstr[2] ""\n"c"\n',
                  encoding="utf-8")
    assert _catalog(po) == {"": ["Plural-Forms: nplurals=3; plural=0;\n"], "month\x04March": ["marzec"],
                            "{n} play": ["a", "b", "c"]}
    assert _plural_forms(po) == 3
