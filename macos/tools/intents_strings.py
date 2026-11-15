"""Writes the Shortcuts and Siri texts in Apple's format from macos/Lang/<code>.po (XcodeGen's preGenCommand).

App Intents' titles and Siri phrases are read by macOS itself, from <code>.lproj/Localizable.strings and
AppShortcuts.strings in the app, so they can't go through the app's own L(). The files are generated into
App/Resources/IntentsStrings (not committed).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sync_po import APP, CODES, LANG, intent_texts, read_po  # noqa: E402

OUT = APP / "Resources" / "IntentsStrings"


def quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\n") + '"'


def write(path: Path, entries: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{quote(key)} = {quote(value)};" for key, value in entries.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    texts, phrases = intent_texts()
    for code in CODES:
        catalog = read_po(LANG / f"{code}.po")
        write(OUT / f"{code}.lproj" / "Localizable.strings", {t: catalog[t] for t in texts if catalog.get(t)})
        write(OUT / f"{code}.lproj" / "AppShortcuts.strings", {p: catalog[p] for p in phrases if catalog.get(p)})
    print(f"{len(texts)} texts and {len(phrases)} phrases for {len(CODES)} languages in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
