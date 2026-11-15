#!/usr/bin/env python3
"""HLS check: does an HLS radio stream play with this GStreamer?

Plays Polskie Radio Czworka's HLS stream (or, if it gives nothing, other HLS stations from radio-browser)
for up to 15 s, and reads the decoded raw caps and the elements that did the work.

Exit 0: a stream decoded to audio.
Exit 1: a missing GStreamer plugin stopped a stream.
Exit 2: inconclusive (no stream produced audio and none reported a missing plugin: network?).
"""
import json
import sys
import time
import urllib.request

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

try:
    gi.require_version("GstPbutils", "1.0")
    from gi.repository import GstPbutils  # noqa: E402
except (ImportError, ValueError):
    GstPbutils = None

CZWORKA = "https://stream14.polskieradio.pl/pr4/pr4.sdp/playlist.m3u8"
API = "https://de1.api.radio-browser.info/json/stations/search"
UA = "MinimalisticRadio-check/1 (Linux)"
PLAY_SECONDS = 15
FALLBACKS = 4


def hls_stations():
    """Other HLS stations, the most voted first."""
    url = API + "?codec=AAC&order=votes&reverse=true&hidebroken=true&limit=300"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            found = json.load(resp)
    except Exception as exc:  # network trouble is reported as inconclusive later
        print(f"radio-browser query failed: {exc}", flush=True)
        return []
    result = []
    for s in found:
        url = s.get("url_resolved") or s.get("url") or ""
        if (s.get("hls") == 1 or ".m3u8" in url) and url != CZWORKA:
            result.append(((s.get("name") or "?").strip(), url))
    return result[:FALLBACKS]


def elements(bin_):
    """The factory names of every element inside, depth first."""
    names = []
    iterator = bin_.iterate_recurse()
    while True:
        ok, element = iterator.next()
        if ok != Gst.IteratorResult.OK:
            break
        factory = element.get_factory()
        if factory is not None:
            names.append(factory.get_name())
    return names


def probe(url):
    """Return (rate, channels, elements, None) once audio decodes, or (None, None, elements, missing plugin or None)."""
    pipeline = Gst.parse_launch(f'uridecodebin name=src uri="{url}" ! audioconvert ! fakesink name=sink sync=false')
    sink = pipeline.get_by_name("sink")
    got = {"buffers": 0}

    def on_buffer(pad, info):
        got["buffers"] += 1
        return Gst.PadProbeReturn.OK

    sink.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, on_buffer)
    bus = pipeline.get_bus()
    pipeline.set_state(Gst.State.PLAYING)
    missing = None
    deadline = time.monotonic() + PLAY_SECONDS
    try:
        while time.monotonic() < deadline:
            msg = bus.timed_pop_filtered(200 * Gst.MSECOND, Gst.MessageType.ERROR | Gst.MessageType.ELEMENT)
            if msg and msg.type == Gst.MessageType.ELEMENT:
                if GstPbutils is not None and GstPbutils.is_missing_plugin_message(msg):
                    missing = GstPbutils.missing_plugin_message_get_description(msg)
                    print(f"  missing plugin: {missing}", flush=True)
                continue
            if msg:
                err, _debug = msg.parse_error()
                print(f"  error: {err.message}", flush=True)
                if err.domain == "gst-core-error-quark" and err.code == int(Gst.CoreError.MISSING_PLUGIN):
                    missing = missing or err.message
                break
            caps = sink.get_static_pad("sink").get_current_caps()
            if caps and got["buffers"] >= 5 and caps.get_size():
                s = caps.get_structure(0)
                ok_r, rate = s.get_int("rate")
                ok_c, channels = s.get_int("channels")
                if ok_r and ok_c:
                    return rate, channels, elements(pipeline), None
        return None, None, elements(pipeline), missing
    finally:
        pipeline.set_state(Gst.State.NULL)


def main():
    Gst.init(None)
    for factory in ("hlsdemux2", "hlsdemux", "tsdemux", "aacparse", "avdec_aac", "faad"):
        print(f"{factory}: {'yes' if Gst.ElementFactory.find(factory) else 'no'}", flush=True)
    candidates = [("Polskie Radio Czworka (HLS)", CZWORKA)]
    tried_fallbacks = False
    while candidates:
        name, url = candidates.pop(0)
        print(f"{name}: {url}", flush=True)
        try:
            rate, channels, used, missing = probe(url)
        except Exception as exc:  # a bad URL or pipeline is not a missing plugin
            print(f"  error: {exc}", flush=True)
            rate, channels, used, missing = None, None, [], None
        print(f"  elements: {' '.join(used)}", flush=True)
        if missing:
            print(f"FAIL: {name} needs a plugin this GStreamer lacks: {missing}")
            return 1
        if rate:
            print(f"OK: {name} decoded to {rate} Hz, {channels} channel(s)")
            return 0
        print("  no audio", flush=True)
        if not candidates and not tried_fallbacks:
            candidates = hls_stations()
            tried_fallbacks = True
    print("Inconclusive: no HLS stream produced audio (network?)")
    return 2


def run():
    # Exit 1 means "a plugin is missing"; a script error must never look like that.
    try:
        return main()
    except Exception as exc:
        print(f"Inconclusive: script error: {exc!r}")
        return 2


if __name__ == "__main__":
    sys.exit(run())
