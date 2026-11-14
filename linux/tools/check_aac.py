#!/usr/bin/env python3
"""HE-AAC gate: do popular HE-AAC radio streams decode fully with this GStreamer?

Plays each station for up to 15 s and reads the negotiated raw caps. A missing
SBR shows as half the sample rate, a missing PS as mono.

The encoded caps (the core rate and channels the AAC parser reports) are compared
with the decoded caps. HE-AAC has a core rate <= 24000; SBR doubles the rate,
PS turns the single core channel into two.

Exit 1: any SBR-FAIL or PS-FAIL.
Exit 0: at least 3 stations are SBR-proven and at least 1 is PS-proven.
Exit 2: inconclusive (fewer than 4 decoded, or a proof is missing).
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
BITRATE_MAX = 48
LOW_LIMIT = 8


def fetch(query):
    url = API + "?" + query
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def stations():
    queries = [
        "codec=AAC%2B&order=votes&reverse=true&hidebroken=true&limit=8",
        # Low bitrate AAC+ is typically HE-AACv2.
        f"codec=AAC%2B&bitrate_max={BITRATE_MAX}&order=votes&reverse=true"
        f"&hidebroken=true&limit={LOW_LIMIT}",
        "name=Czw%C3%B3rka&hidebroken=true&limit=20",
    ]
    found = []
    for query in queries:
        try:
            found.extend(fetch(query))
        except Exception as exc:  # network trouble is reported as inconclusive later
            print(f"radio-browser query failed: {exc}", flush=True)
    if not any("czw" in s.get("name", "").lower() for s in found):
        try:
            found.extend(fetch("name=Polskie%20Radio&codec=AAC%2B&hidebroken=true&limit=5"))
            print("Czworka not found; using Polskie Radio AAC+ stations instead", flush=True)
        except Exception as exc:
            print(f"radio-browser query failed: {exc}", flush=True)
    seen, result = set(), []
    for s in found:
        if (s.get("codec") or "").upper() not in ("AAC", "AAC+"):
            continue
        url = s.get("url_resolved") or s.get("url")
        if url and url not in seen:
            seen.add(url)
            result.append(((s.get("name") or "?").strip(), url))
    return result


def probe(url):
    """Return ((enc_rate, enc_ch), (dec_rate, dec_ch)) or None if nothing came out."""
    pipeline = Gst.parse_launch(
        f'uridecodebin name=src uri="{url}" ! audioconvert ! fakesink name=sink sync=false'
    )
    sink = pipeline.get_by_name("sink")
    got = {"buffers": 0, "enc": None}

    def on_continue(_bin, _pad, caps):
        for i in range(caps.get_size()):
            st = caps.get_structure(i)
            if st.get_name() == "audio/mpeg" and st.get_int("mpegversion")[1] in (2, 4):
                ok_r, rate = st.get_int("rate")
                ok_c, ch = st.get_int("channels")
                if ok_r and ok_c:
                    got["enc"] = (rate, ch)
        return True

    pipeline.get_by_name("src").connect("autoplug-continue", on_continue)

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
            if caps and got["buffers"] >= 5 and caps.get_size() and got["enc"]:
                s = caps.get_structure(0)
                ok_r, rate = s.get_int("rate")
                ok_c, channels = s.get_int("channels")
                if ok_r and ok_c:
                    result = (got["enc"], (rate, channels))
                    break
    finally:
        pipeline.set_state(Gst.State.NULL)
    return result


def verdicts(enc, dec):
    er, ec = enc
    dr, dc = dec
    out = []
    if er > 24000:
        return ["LC"]
    if dr >= 2 * er:
        out.append("SBR-proven")
    elif dr == er:
        out.append("SBR-FAIL")
    if ec == 1 and dc == 2:
        out.append("PS-proven")
    elif ec == 1 and dc == 1 and "SBR-proven" in out:
        out.append("PS-FAIL")
    return out or ["unclear"]


def main():
    Gst.init(None)
    sbr = ps = fails = decoded = 0
    for name, url in stations():
        try:
            r = probe(url)
        except Exception as exc:  # a bad URL or pipeline is not a codec failure
            print(f"  error: {exc}", flush=True)
            r = None
        if not r:
            print(f"{name}, -, -, -, -, NO AUDIO", flush=True)
            continue
        (er, ec), (dr, dc) = r
        v = verdicts((er, ec), (dr, dc))
        decoded += 1
        sbr += "SBR-proven" in v
        ps += "PS-proven" in v
        fails += any(x.endswith("FAIL") for x in v)
        print(f"{name}, {er}, {ec}, {dr}, {dc}, {' '.join(v)}", flush=True)

    print(f"decoded={decoded} SBR-proven={sbr} PS-proven={ps} fails={fails}")
    if fails:
        return 1
    if decoded < 4:
        print("Inconclusive: fewer than 4 stations produced audio (network?)")
        return 2
    if sbr >= 3 and ps >= 1:
        return 0
    missing = []
    if sbr < 3:
        missing.append(f"SBR proven on only {sbr} stations (need 3)")
    if ps < 1:
        missing.append("no HE-AACv2 (PS) station among the candidates")
    print("Inconclusive: " + "; ".join(missing))
    return 2


def run():
    # Exit 1 means "the decoder fails"; a script error must never look like that.
    try:
        return main()
    except Exception as exc:
        print(f"Inconclusive: script error: {exc!r}")
        return 2


if __name__ == "__main__":
    sys.exit(run())
