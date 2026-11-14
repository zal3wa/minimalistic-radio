"""Translations: gettext with the language chosen in the settings ("auto" follows the system)."""
from __future__ import annotations

import gettext
import os
from typing import Callable

DOMAIN = "minimalistic-radio"

_translation: gettext.NullTranslations = gettext.NullTranslations()


def system_languages() -> list[str]:
    """The user's languages in order of preference, from the usual environment variables."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return [code for code in value.split(":") if code]
    return []


def languages_for(setting: str, system: list[str]) -> list[str]:
    if setting in ("pl", "en"):
        return [setting]
    return list(system)


def install(setting: str, localedir: str) -> Callable[[str], str]:
    """Loads the translation for `setting` and returns its gettext function (English if there is none)."""
    global _translation
    _translation = gettext.translation(DOMAIN, localedir, languages=languages_for(setting, system_languages()) or None,
                                       fallback=True)
    return _translation.gettext


def N_(singular: str, plural: str, n: int) -> str:
    """ngettext for the installed language."""
    return _translation.ngettext(singular, plural, n)
