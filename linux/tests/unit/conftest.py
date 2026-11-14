"""Shared unit-test fixtures."""
from __future__ import annotations

import itertools

import pytest

from fakes import A, B, C, FakeFetch, FakePlayer, FakeScheduler
from minimalistic_radio.controller import RadioController
from minimalistic_radio.core.storage import Paths, save_history, save_preferences, save_stations


@pytest.fixture
def ctl_factory(tmp_path):
    """Makes a RadioController over fakes, with these files already saved. Call start() yourself."""
    counter = itertools.count(1)

    def make(stations=(A, B, C), prefs=None, history=None):
        root = tmp_path / f"ctl{next(counter)}"
        paths = Paths(root / "config", root / "data", root / "cache")
        save_stations(paths.config / "stations.json", list(stations))
        if prefs is not None:
            save_preferences(paths.config / "preferences.json", prefs)
        if history is not None:
            save_history(paths.data / "history.json", history)
        fetch = FakeFetch()
        return RadioController(FakePlayer(), FakeScheduler(), paths, fetch, fetch.file)

    return make


@pytest.fixture
def ctl(ctl_factory):
    """Started with stations A, B, C and default preferences; nothing selected, nothing playing."""
    controller = ctl_factory()
    controller.start(autostart=True)
    return controller


@pytest.fixture
def ctl_playing(ctl_factory):
    """Two stations, the first playing at volume 30 with a song on."""
    from minimalistic_radio.core.models import Preferences, Station
    controller = ctl_factory(stations=(Station("Radio A", "http://a.example/live"),
                                       Station("Radio B", "http://b.example/live")),
                             prefs=Preferences(volume=30))
    controller.start(autostart=True)
    controller.select(0)
    controller.play()
    controller.on_player_started()
    controller.track = "Leonard Cohen - Everybody Knows"
    return controller


@pytest.fixture
def empty_ctl(ctl_factory):
    controller = ctl_factory(stations=())
    controller.start(autostart=True)
    return controller


def item(items, id):
    return next(i for i in items if i.id == id)
