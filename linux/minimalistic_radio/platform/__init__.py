import os

SNAP_NAME = "minimalistic-radio"


def in_snap() -> bool:
    """Running in this app's Snap. Another snap's variables (leaked into a terminal, say) don't count."""
    return os.environ.get("SNAP_NAME") == SNAP_NAME
