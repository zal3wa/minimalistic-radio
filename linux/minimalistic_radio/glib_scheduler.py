"""The controller's Scheduler on the GLib main loop."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402


class _Timer:
    def __init__(self) -> None:
        self.source = 0
        self.done = False


class GLibScheduler:
    def call_later(self, seconds: float, cb: Callable[[], None]) -> object:
        timer = _Timer()

        def fire() -> bool:
            timer.done = True
            cb()
            return GLib.SOURCE_REMOVE

        timer.source = GLib.timeout_add(max(0, int(seconds * 1000)), fire)
        return timer

    def cancel(self, handle: object) -> None:
        if isinstance(handle, _Timer) and not handle.done:
            handle.done = True
            GLib.source_remove(handle.source)

    def now(self) -> datetime:
        return datetime.now()
