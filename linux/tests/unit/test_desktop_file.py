"""The desktop file makes the radio the handler of minimalistic-radio:// links (the share page's button)."""
from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[2] / "data" / "io.github.zal3wa.minimalistic-radio.desktop.in"


def test_the_radio_opens_its_links():
    lines = DESKTOP.read_text(encoding="utf-8").splitlines()
    assert "MimeType=x-scheme-handler/minimalistic-radio;" in lines
    assert "Exec=minimalistic-radio %u" in lines   # the link arrives as an argument
