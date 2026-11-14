"""Temporary (CI only): hammers GstPlayer with quick station changes to catch a teardown crash.

Usage: python3 tests/integration/stress_player.py SEED [ACTIONS]   (from linux/)
"""
import faulthandler
import random
import socket
import sys
import tempfile
import time
from pathlib import Path

faulthandler.enable()
sys.path[:0] = [".", "tests/integration"]

import gi  # noqa: E402

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

from icy_server import IcyServer  # noqa: E402
from minimalistic_radio.audio.player import GstPlayer  # noqa: E402


def fakesink():
    sink = Gst.ElementFactory.make("fakesink", None)
    sink.set_property("sync", True)
    return sink


def pump(seconds):
    context = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while context.iteration(False):
            pass
        time.sleep(0.002)


def main():
    seed = int(sys.argv[1])
    actions = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    rng = random.Random(seed)
    server = IcyServer(Path(tempfile.mkdtemp()))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        closed = f"http://127.0.0.1:{s.getsockname()[1]}/mp3"
    urls = [server.url(p) for p in ("/mp3", "/aac", "/opus", "/changing", "/403", "/list.pls", "/once")] + [closed]
    events = {"started": 0, "title": 0, "error": 0, "eos": 0}

    def count(name):
        def callback(*_args):
            events[name] += 1
        return callback

    player = GstPlayer(count("started"), count("title"), count("error"), count("eos"),
                       audio_sink_factory=fakesink)
    print(f"seed {seed}, {actions} actions, missing {sorted(server.missing)}", flush=True)
    for i in range(actions):
        roll = rng.random()
        if roll < 0.7:
            player.play(rng.choice(urls))
        elif roll < 0.85:
            player.stop()
        else:
            player.set_volume(rng.randrange(101))
        wait = rng.random()
        if wait < 0.3:
            pass                                   # the next action at once
        elif wait < 0.6:
            time.sleep(rng.random() * 0.2)         # the pipeline runs, the main loop doesn't
        else:
            pump(rng.random() * 0.6)
        if i % 50 == 0:
            print(f"{i}: {events}", flush=True)
    player.stop()
    pump(0.5)
    server.close()
    print(f"done: {events}", flush=True)


if __name__ == "__main__":
    main()
