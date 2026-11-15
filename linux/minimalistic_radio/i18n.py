"""Translations: gettext with the language chosen in the settings ("auto" follows the system).

Everyone translates through gettext() below, which reads the installed translation on every call, so
choosing another language (install() again) reaches the controller, the player and the tray as well.
"""
from __future__ import annotations

import gettext as _gettext
import os
import re
from typing import Callable

DOMAIN = "minimalistic-radio"

_translation: _gettext.NullTranslations = _gettext.NullTranslations()


def system_languages() -> list[str]:
    """The user's languages in order of preference, from the usual environment variables."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return [code for code in value.split(":") if code]
    return []


SUPPORTED = ("pl", "en", "de", "uk", "cs", "es", "fr", "it", "pt")


def languages_for(setting: str, system: list[str]) -> list[str]:
    """[the language to use]: the chosen one, or for "auto" the first supported language of `system`
    (["uk_UA", "en"] gives ["uk"]), else English."""
    if setting in SUPPORTED:
        return [setting]
    for entry in system:
        code = re.split(r"[_.@-]", entry, maxsplit=1)[0].lower()
        if code in SUPPORTED:
            return [code]
    return ["en"]


def gettext(message: str) -> str:
    """`message` in the installed language (English if there is no translation)."""
    return _translation.gettext(message)


def install(setting: str, localedir: str) -> Callable[[str], str]:
    """Loads the translation for `setting` and returns gettext (English if there is none)."""
    global _translation
    _translation = _gettext.translation(DOMAIN, localedir, languages=languages_for(setting, system_languages()) or None,
                                        fallback=True)
    return gettext


def N_(singular: str, plural: str, n: int) -> str:
    """ngettext for the installed language."""
    return _translation.ngettext(singular, plural, n)
