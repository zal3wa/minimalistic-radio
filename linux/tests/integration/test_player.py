"""GstPlayer against the local test server, driven on a GLib main loop (10 s at most per wait).

Sound goes to a fakesink that keeps real time (sync), so no audio server is needed.
"""
from __future__ import annotations

import socket
import time

import gi
import pytest

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

from icy_server import CHANGING_TITLES, CP1250_TITLE, TITLE  # noqa: E402
from minimalistic_radio import APP_ID, APP_NAME  # noqa: E402
from minimalistic_radio.audio.player import GstPlayer, make_audio_sink  # noqa: E402
from minimalistic_radio.controller import ErrorKind  # noqa: E402
from minimalistic_radio.core.net import USER_AGENT  # noqa: E402

TIMEOUT = 10.0


def _fakesink():
    sink = Gst.ElementFactory.make("fakesink", None)
    sink.set_property("sync", True)
    return sink


class Recorder:
    """The player's four callbacks. Also notes any callback made from inside play(), stop() or set_volume()."""

    def __init__(self) -> None:
        self.started = 0
        self.titles: list[str] = []
        self.errors: list[tuple[ErrorKind, str]] = []
        self.eos = 0
        self.inside_call = False
        self.reentrant: list[str] = []

    def _note(self, name: str) -> None:
        if self.inside_call:
            self.reentrant.append(name)

    def on_started(self) -> None:
        self._note("started")
        self.started += 1

    def on_title(self, raw: str) -> None:
        self._note("title")
        self.titles.append(raw)

    def on_error(self, kind: ErrorKind, detail: str) -> None:
        self._note("error")
        self.errors.append((kind, detail))

    def on_eos(self) -> None:
        self._note("eos")
        self.eos += 1

    @property
    def events(self) -> int:
        return self.started + len(self.titles) + len(self.errors) + self.eos


class Driver:
    def __init__(self) -> None:
        self.rec = Recorder()
        self.player = GstPlayer(self.rec.on_started, self.rec.on_title, self.rec.on_error, self.rec.on_eos,
                                audio_sink_factory=_fakesink)

    def call(self, method: str, *args) -> None:
        self.rec.inside_call = True
        try:
            getattr(self.player, method)(*args)
        finally:
            self.rec.inside_call = False

    def run(self, until=lambda: False, timeout: float = TIMEOUT) -> bool:
        """Runs the main loop until `until()` holds or `timeout` seconds pass; returns `until()`."""
        loop = GLib.MainLoop()
        deadline = time.monotonic() + timeout

        def check() -> bool:
            if until() or time.monotonic() >= deadline:
                loop.quit()
                return False
            return True

        GLib.timeout_add(20, check)
        loop.run()
        return bool(until())

    def playing_with_title(self) -> bool:
        return self.rec.started > 0 and TITLE in self.rec.titles


@pytest.fixture
def drv():
    driver = Driver()
    yield driver
    driver.call("stop")
    assert driver.rec.reentrant == [], "a callback came from inside play(), stop() or set_volume()"


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("fmt", ["mp3", "aac", "heaac", "opus"])
def test_plays_and_reads_titles(drv, icy, fmt):
    if fmt in icy.missing:
        if fmt == "heaac":
            pytest.skip(f"no HE-AAC test stream: {icy.missing[fmt]}")
        pytest.fail(f"couldn't make the {fmt} test stream: {icy.missing[fmt]}")
    drv.call("play", icy.url(f"/{fmt}"))
    assert drv.run(drv.playing_with_title), (drv.rec.started, drv.rec.titles, drv.rec.errors)
    assert drv.rec.started == 1 and drv.rec.errors == []


def test_icy_title_cp1250(drv, icy):
    drv.call("play", icy.url("/cp1250"))
    assert drv.run(lambda: drv.rec.titles), drv.rec.errors
    assert drv.rec.titles[0] == CP1250_TITLE


def test_title_reported_again_only_after_it_changes(drv, icy):
    # Every title comes twice in a row from the server, then the other one.
    drv.call("play", icy.url("/changing"))
    assert drv.run(lambda: len(drv.rec.titles) >= 3), (drv.rec.titles, drv.rec.errors)
    first, second = CHANGING_TITLES
    assert drv.rec.titles[:3] == [first, second, first]


def test_refused_403(drv, icy):
    drv.call("play", icy.url("/403"))
    assert drv.run(lambda: drv.rec.errors)
    assert drv.rec.errors[0] == (ErrorKind.REFUSED, "The station's server refused access (403).")
    assert drv.rec.started == 0


def test_unreachable_is_network(drv):
    drv.call("play", f"http://127.0.0.1:{_closed_port()}/mp3")
    assert drv.run(lambda: drv.rec.errors)
    drv.run(timeout=0.5)
    assert drv.rec.errors == [
        (ErrorKind.NETWORK, "Couldn't connect to the station. Check your internet connection.")]


def test_end_of_stream(drv, icy):
    drv.call("play", icy.url("/once"))
    assert drv.run(lambda: drv.rec.eos), drv.rec.errors
    assert drv.rec.started == 1 and drv.rec.errors == [] and drv.rec.eos == 1


def test_playlist_resolves_first_stream(drv, icy):
    drv.call("play", icy.url("/list.pls"))
    assert drv.run(drv.playing_with_title), (drv.rec.started, drv.rec.titles, drv.rec.errors)


def test_playlist_found_by_content_type(drv, icy):
    drv.call("play", icy.url("/playlist"))      # no .pls in the address, only audio/x-scpls
    assert drv.run(drv.playing_with_title), (drv.rec.started, drv.rec.titles, drv.rec.errors)


def test_stream_request_names_the_app(drv, icy):
    drv.call("play", icy.url("/mp3?user-agent"))
    assert drv.run(lambda: drv.rec.started)
    assert ("/mp3?user-agent", USER_AGENT) in icy.requests


def test_stream_named_in_mixer():
    sink = make_audio_sink()
    assert sink is not None and sink.get_factory().get_name() in ("pulsesink", "pipewiresink")
    properties = sink.get_property("stream-properties")
    assert properties.get_string("application.name") == APP_NAME
    assert properties.get_string("application.icon_name") == APP_ID
    assert properties.get_string("media.role") == "music"


# ---- The Player contract (controller.py) ----

def test_stop_drops_a_playlist_already_queued(drv, icy):
    drv.call("play", icy.url("/list.pls"))
    time.sleep(1)              # the playlist arrives and waits on the main loop
    drv.call("stop")
    drv.run(timeout=2)
    assert drv.rec.events == 0


def test_stop_drops_a_playlist_still_loading(drv, icy):
    drv.call("play", icy.url("/slow.pls"))     # answered after a second
    drv.call("stop")
    drv.run(timeout=2.5)
    assert drv.rec.events == 0


def test_play_drops_the_previous_stream(drv, icy):
    drv.call("play", icy.url("/403"))
    time.sleep(1)              # the refusal waits on the bus
    drv.call("play", icy.url("/mp3"))
    assert drv.run(drv.playing_with_title), (drv.rec.titles, drv.rec.errors)
    assert drv.rec.errors == []


def test_nothing_after_stop(drv, icy):
    drv.call("play", icy.url("/changing"))
    assert drv.run(lambda: drv.rec.titles)
    time.sleep(1.5)            # the next title waits on the bus
    drv.call("stop")
    seen = drv.rec.events
    drv.run(timeout=1.5)
    assert drv.rec.events == seen


def test_switching_stations_quickly(drv, icy):
    # Each playbin is dropped at a different moment of its start (up to about 0.2 s in).
    for i in range(20):
        drv.call("play", icy.url("/mp3" if i % 2 else "/aac"))
        time.sleep(i * 0.01)
    drv.call("stop")
    drv.call("play", icy.url("/mp3"))
    assert drv.run(drv.playing_with_title), (drv.rec.titles, drv.rec.errors)
    assert drv.rec.errors == []


def test_volume_persists_across_play(drv, icy):
    drv.call("set_volume", 50)
    drv.call("play", icy.url("/mp3"))
    assert drv.run(lambda: drv.rec.started)
    assert drv.player._playbin.get_property("volume") == pytest.approx(0.5 ** 3)   # cubic, like the slider
    drv.call("stop")
    drv.call("set_volume", 20)
    drv.call("play", icy.url("/mp3"))
    assert drv.player._playbin.get_property("volume") == pytest.approx(0.2 ** 3)
    drv.call("set_volume", 100)
    assert drv.player._playbin.get_property("volume") == pytest.approx(1.0)
