"""Entry point: picks the language, then runs the application."""
from __future__ import annotations

import sys

from . import APP_NAME
from .core.storage import default_paths, load_preferences

# The launcher (bin/minimalistic-radio.in) sets these to the installed locations.
LOCALEDIR = "/usr/share/locale"
PKGDATADIR = "/usr/share/minimalistic-radio"


def main(argv: list[str]) -> int:
    from gi.repository import GLib

    GLib.set_application_name(APP_NAME)   # before the player exists: names the stream for the sound settings
    from . import i18n
    from .app import RadioApplication

    try:
        language = load_preferences(default_paths().config / "preferences.json").language
    except OSError:
        language = "auto"
    translate = i18n.install(language, LOCALEDIR)
    return RadioApplication(translate=translate).run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
