"""Fills macos/Lang/<code>.po with every text the Mac app shows, and lists the ones still to translate.

Run it after changing texts in macos/App (Python 3, any system): python macos/tools/sync_po.py

- The texts are the English literals in L("...") calls under macos/App and macos/Core/Sources.
- Each translation comes from, in order: the Mac catalogue itself, the Windows one (src/Lang/<code>.po), then the
  Linux one (linux/po/<code>.po). Texts the Mac no longer uses are dropped.
- Whatever is still untranslated is printed per language; translate it in macos/Lang/<code>.po by hand.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "macos" / "App"
CORE = ROOT / "macos" / "Core" / "Sources"
LANG = ROOT / "macos" / "Lang"
CODES = ("pl", "de", "uk", "cs", "es", "fr", "it", "pt")
LITERAL = re.compile(r'\bL\(\s*"((?:[^"\\]|\\.)*)"')
NAMES = {"pl": "Polish", "de": "German", "uk": "Ukrainian", "cs": "Czech", "es": "Spanish", "fr": "French",
         "it": "Italian", "pt": "Portuguese"}


def swift_unescape(text: str) -> str:
    def replace(match: re.Match) -> str:
        code = match.group(1)
        if code.startswith("u{"):
            return chr(int(code[2:-1], 16))
        return {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "'": "'", "0": "\0"}.get(code, code)
    return re.sub(r"\\(u\{[0-9A-Fa-f]+\}|.)", replace, text)


def po_unquote(text: str) -> str:
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), text)


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def read_po(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    if not path.exists():
        return entries
    msgid = msgstr = None
    field = None

    def finish() -> None:
        if msgid and msgstr:
            entries[msgid] = msgstr

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("msgid "):
            finish()
            msgid, msgstr, field = po_unquote(line[6:]), None, "id"
        elif line.startswith("msgstr "):
            msgstr, field = po_unquote(line[7:]), "str"
        elif line.startswith('"'):
            if field == "id":
                msgid += po_unquote(line)
            elif field == "str":
                msgstr += po_unquote(line)
        elif line.startswith(("msgid_plural", "msgstr[")):
            field = None
    finish()
    return entries


def used_texts() -> list[str]:
    seen: dict[str, None] = {}
    for path in sorted(APP.rglob("*.swift")) + sorted(CORE.rglob("*.swift")):
        for match in LITERAL.finditer(path.read_text(encoding="utf-8")):
            seen.setdefault(swift_unescape(match.group(1)), None)
    return list(seen)


def write_po(path: Path, code: str, entries: list[tuple[str, str]]) -> None:
    lines = [f"# {NAMES[code]} translation of Minimalistic Radio for macOS.",
             "# The English text is the msgid. Corrections by native speakers are welcome.",
             'msgid ""', 'msgstr ""', f'"Language: {code}\\n"', '"Content-Type: text/plain; charset=UTF-8\\n"', ""]
    for msgid, msgstr in entries:
        lines += [f"msgid {po_quote(msgid)}", f"msgstr {po_quote(msgstr)}", ""]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    texts = used_texts()
    LANG.mkdir(parents=True, exist_ok=True)
    total_missing = 0
    for code in CODES:
        sources = [read_po(LANG / f"{code}.po"), read_po(ROOT / "src" / "Lang" / f"{code}.po"),
                   read_po(ROOT / "linux" / "po" / f"{code}.po")]
        entries = []
        missing = []
        for text in texts:
            translation = next((source[text] for source in sources if source.get(text)), "")
            entries.append((text, translation))
            if not translation:
                missing.append(text)
        write_po(LANG / f"{code}.po", code, entries)
        total_missing += len(missing)
        for text in missing:
            print(f"{code}: {text!r}")
    print(f"{len(texts)} texts, {total_missing} untranslated entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
