"""Sets translations in macos/Lang/<code>.po: python macos/tools/translate.py translations.json

translations.json: {"English text": {"pl": "...", "de": "...", ...}, ...}. Used with sync_po.py for the texts
that neither the Windows nor the Linux catalogue has.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sync_po import CODES, LANG, read_po, used_texts, write_po  # noqa: E402

wanted = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
texts = used_texts()
for code in CODES:
    catalog = read_po(LANG / f"{code}.po")
    for english, translations in wanted.items():
        if code in translations:
            catalog[english] = translations[code]
    write_po(LANG / f"{code}.po", code, [(text, catalog.get(text, "")) for text in texts])
print("ok")
