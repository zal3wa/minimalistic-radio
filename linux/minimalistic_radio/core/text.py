"""Texts from outside (station names, song titles), made safe to show the same way on every system.

Names come from share links, radio-browser, the station form, an imported list and the station file; titles from
the stream. Both lose control characters and the bidirectional formatting characters, which can make a text show
in another order than it is written (U+202E turns the rest of the line around). Zero-width joiners and variation
selectors stay: emoji need them.
"""
from __future__ import annotations

import unicodedata

MAX_NAME = 100

_BIDI = frozenset("؜‎‏‪‫‬‭‮⁦⁧⁨⁩")


def clean_chars(text: str) -> str:
    """`text` without control characters and bidirectional formatting characters."""
    return "".join(c for c in text if c not in _BIDI and unicodedata.category(c) != "Cc")


def clean_name(text: str | None) -> str:
    """A station name: cleaned, trimmed and at most MAX_NAME characters; '' when nothing is left."""
    return clean_chars(text or "").strip()[:MAX_NAME].rstrip()


def notification_text(text: str) -> str:
    """< and > become ‹ and ›: some notification servers read the text as markup."""
    return text.replace("<", "‹").replace(">", "›")
