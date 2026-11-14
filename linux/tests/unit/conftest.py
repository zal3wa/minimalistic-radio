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
