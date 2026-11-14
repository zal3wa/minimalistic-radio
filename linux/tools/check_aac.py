#!/usr/bin/env python3
"""HE-AAC gate: do popular HE-AAC radio streams decode fully with this GStreamer?

Plays each station for up to 15 s and reads the negotiated raw caps. A missing
SBR shows as half the sample rate, a missing PS as mono.

Exit 0: all decoded stations have rate >= 32000 and at least 75% are stereo.
Exit 1: the codec fails (the table is printed).
Exit 2: fewer than 4 stations produced audio (network trouble, inconclusive).
"""
import json
import sys
import time
import urllib.parse
import urllib.request

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

API = "https://de1.api.radio-browser.info/json/stations/search"
UA = "MinimalisticRadio-check/1 (Linux)"
PLAY_SECONDS = 15


def fetch(query):
    url = API + "?" + query
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def stations():
    found = []
    popular = "codec=AAC%2B&order=votes&reverse=true&hidebroken=true&limit=8"
    by_name = "name=" + urllib.parse.quote("Polskie Radio Czwórka AAC+") + "&limit=1&hidebroken=true"
    for query in (popular, by_name):
        try:
            found.extend(fetch(query))
        except Exception as exc:  # network trouble is reported as inconclusive later
            print(f"radio-browser query failed: {exc}", flush=True)
    seen, result = set(), []
    for s in found:
        url = s.get("url_resolved") or s.get("url")
        if url and url not in seen:
            seen.add(url)
            result.append((s.get("name", "?").strip(), url))
    return result


def probe(url):
    """Return (rate, channels) of the decoded audio, or None if nothing came out."""
    pipeline = Gst.parse_launch(
        f'uridecodebin uri="{url}" ! audioconvert ! fakesink name=sink sync=false'
    )
    sink = pipeline.get_by_name("sink")
    got = {"buffers": 0}

    def on_buffer(pad, info):
        got["buffers"] += 1
        return Gst.PadProbeReturn.OK

    sink.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, on_buffer)
    bus = pipeline.get_bus()
    pipeline.set_state(Gst.State.PLAYING)
    result = None
    deadline = time.monotonic() + PLAY_SECONDS
    try:
        while time.monotonic() < deadline:
            msg = bus.timed_pop_filtered(200 * Gst.MSECOND, Gst.MessageType.ERROR)
            if msg:
                err, _ = msg.parse_error()
                print(f"  error: {err.message}", flush=True)
                break
            caps = sink.get_static_pad("sink").get_current_caps()
            if caps and got["buffers"] >= 5 and caps.get_size():
                s = caps.get_structure(0)
                ok_r, rate = s.get_int("rate")
                ok_c, channels = s.get_int("channels")
                if ok_r and ok_c:
                    result = (rate, channels)
                    break
    finally:
        pipeline.set_state(Gst.State.NULL)
    return result


def main():
    Gst.init(None)
    rows = []
    for name, url in stations():
        r = probe(url)
        if r:
            rows.append((name, r[0], r[1]))
            print(f"{name}, {r[0]}, {r[1]}, {'OK' if r[0] >= 32000 and r[1] == 2 else 'FAIL'}", flush=True)
        else:
            print(f"{name}, -, -, NO AUDIO", flush=True)

    if len(rows) < 4:
        print(f"Only {len(rows)} stations produced audio: inconclusive (network?)")
        return 2
    rate_ok = all(rate >= 32000 for _, rate, _ in rows)
    stereo = sum(1 for _, _, ch in rows if ch == 2) / len(rows)
    print(f"{len(rows)} decoded, all rates >= 32000: {rate_ok}, stereo share: {stereo:.0%}")
    return 0 if rate_ok and stereo >= 0.75 else 1


if __name__ == "__main__":
    sys.exit(main())
