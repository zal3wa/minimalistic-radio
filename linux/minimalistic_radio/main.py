"""Entry point: picks the language, then runs the application."""
from __future__ import annotations

import sys
from pathlib import Path

from . import APP_NAME
from .core.storage import default_paths, load_preferences

# The launcher (bin/minimalistic-radio.in) sets these to the installed locations.
LOCALEDIR = "/usr/share/locale"
PKGDATADIR = "/usr/share/minimalistic-radio"


def load_bans() -> None:
    """The list of stations never shown: the installed one, else the source tree's."""
    from .core import directory
    for folder in (Path(PKGDATADIR), Path(__file__).resolve().parents[1] / "data"):
        if (folder / "banned-stations.json").is_file():
            directory.use_bans(directory.load_banned(folder / "banned-stations.json"))
            return


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
    load_bans()
    return RadioApplication(translate=translate).run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
