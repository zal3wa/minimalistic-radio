"""Test doubles for RadioController: a player, a clock with timers, and the network."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from minimalistic_radio.core.models import Station


class FakePlayer:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def play(self, url: str) -> None:
        self.calls.append(("play", url))

    def stop(self) -> None:
        self.calls.append(("stop",))

    def set_volume(self, percent: int) -> None:
        self.calls.append(("set_volume", percent))


class FakeScheduler:
    """A clock that only moves on advance(), running the callbacks that fall due on the way."""

    def __init__(self, start: datetime = datetime(2026, 11, 14, 12, 0, 0)) -> None:
        self.start = start
        self.time = 0.0
        self._timers: dict[int, tuple[float, Callable[[], None]]] = {}
        self._next_id = 0

    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.time)

    def call_later(self, seconds: float, cb: Callable[[], None]) -> object:
        self._next_id += 1
        self._timers[self._next_id] = (self.time + seconds, cb)
        return self._next_id

    def cancel(self, handle: object) -> None:
        self._timers.pop(handle, None)

    def pending(self) -> int:
        return len(self._timers)

    def next_delay(self) -> float | None:
        if not self._timers:
            return None
        return min(due for due, _ in self._timers.values()) - self.time

    def advance(self, seconds: float) -> None:
        target = self.time + seconds
        while self._timers:
            handle, (due, cb) = min(self._timers.items(), key=lambda item: (item[1][0], item[0]))
            if due > target:
                break
            del self._timers[handle]
            self.time = due
            cb()
        self.time = target


class FakeFetch:
    """fetch (JSON) and fetch_file (downloads). Answers at once from `responses`, otherwise waits for reply()."""

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.responses: dict[str, Any] = {}
        self.pending: list[tuple[str, Callable[[Any | None], None]]] = []
        self.downloads: list[tuple[str, Path, Callable[[bool], None]]] = []

    def __call__(self, url: str, callback: Callable[[Any | None], None]) -> None:
        self.urls.append(url)
        if url in self.responses:
            callback(self.responses[url])
        else:
            self.pending.append((url, callback))

    def reply(self, payload: Any | None) -> None:
        """Answers the oldest request still waiting (None means it failed)."""
        _, callback = self.pending.pop(0)
        callback(payload)

    def file(self, url: str, path: Path, callback: Callable[[bool], None]) -> None:
        self.downloads.append((url, path, callback))

    def finish_download(self, ok: bool = True) -> None:
        url, path, callback = self.downloads.pop(0)
        if ok:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"\xff\xd8 cover of " + url.encode())
        callback(ok)


# Sample stations for tests (A, B and C are what the `ctl` fixture starts with).
A = Station("Alpha", "http://a.example/live")
B = Station("Beta", "http://b.example/live", "https://b.example/logo.png")
C = Station("Gamma", "https://c.example/stream")
