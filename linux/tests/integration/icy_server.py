"""A small Shoutcast-style server for the player tests, on 127.0.0.1 and a free port.

The test streams are made at start with gst-launch-1.0 (a sine tone, about 23 s, sent in a loop). ICY
metadata goes every 8 KiB when the request has `Icy-MetaData: 1`, as real stations do.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

TITLE = "Test Artist - Test Title"
CP1250_TITLE = "Dawid Podsiadło - Małomiasteczkowy"
CHANGING_TITLES = ("First Artist - First Song", "Second Artist - Second Song")
METAINT = 8192
SOURCE = "audiotestsrc num-buffers=1000 ! audioconvert ! audioresample"


def _mp3(data: bytes) -> bool:
    return len(data) > 4 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0


def _adts(data: bytes) -> bool:
    return len(data) > 7 and data[0] == 0xFF and data[1] & 0xF6 == 0xF0


def _he_aac(data: bytes) -> bool:
    # HE-AAC in ADTS carries the AAC core's rate (half the output rate): 24 kHz or lower.
    return _adts(data) and (data[2] >> 2) & 0x0F >= 6


def _ogg(data: bytes) -> bool:
    return data[:4] == b"OggS"


# name: (Content-Type, check of the encoded file, encoder chains tried in order)
FORMATS = {
    "mp3": ("audio/mpeg", _mp3, ["lamemp3enc target=bitrate bitrate=128 cbr=true"]),
    "aac": ("audio/aac", _adts, [
        "avenc_aac bitrate=128000 ! aacparse ! audio/mpeg,mpegversion=4,stream-format=adts",
        "avenc_aac bitrate=128000 ! avmux_adts",
    ]),
    "heaac": ("audio/aacp", _he_aac, [
        "audio/x-raw,rate=44100,channels=2 ! fdkaacenc bitrate=48000"
        " ! audio/mpeg,mpegversion=4,stream-format=adts,profile=he-aac-v1",
    ]),
    "opus": ("audio/ogg", _ogg, ["opusenc bitrate=64000 ! oggmux"]),
}


def _encode(chain: str, path: Path) -> str | None:
    """Runs one gst-launch-1.0 pipeline; returns why it failed, or None."""
    command = ["gst-launch-1.0", "-q", *SOURCE.split(), "!", *chain.split(), "!", "filesink", f"location={path}"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    if result.returncode != 0:
        return (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
    return None


def _metadata(title: bytes) -> bytes:
    body = b"StreamTitle='" + title + b"';"
    blocks = -(-len(body) // 16)
    return bytes([blocks]) + body.ljust(blocks * 16, b"\0")


def _playlist(target: str) -> bytes:
    return f"[playlist]\nNumberOfEntries=1\nFile1={target}\nTitle1=Test\nLength1=-1\nVersion=2\n".encode()


class IcyServer:
    def __init__(self, folder: Path) -> None:
        self.streams: dict[str, tuple[bytes, str]] = {}   # name: (encoded audio, Content-Type)
        self.missing: dict[str, str] = {}                 # name: why it couldn't be made
        if shutil.which("gst-launch-1.0") is None:
            self.missing = {name: "gst-launch-1.0 is not installed" for name in FORMATS}
        else:
            for name, (content_type, check, chains) in FORMATS.items():
                reasons = []
                for chain in chains:
                    path = folder / f"{name}.bin"
                    reason = _encode(chain, path)
                    data = path.read_bytes() if reason is None and path.exists() else b""
                    if reason is None and check(data):
                        self.streams[name] = (data, content_type)
                        break
                    reasons.append(f"{chain}: {reason or 'wrong output'}")
                else:
                    self.missing[name] = "; ".join(reasons)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.daemon_threads = True
        self._httpd.icy = self  # type: ignore[attr-defined]
        self.port = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, name="icy-server", daemon=True).start()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        icy: IcyServer = self.server.icy  # type: ignore[attr-defined]
        path = urlsplit(self.path).path
        mp3 = icy.streams.get("mp3")
        if path == "/403":
            self._answer(403, "text/plain", b"Forbidden")
        elif path in ("/list.pls", "/playlist", "/slow.pls"):
            if path == "/slow.pls":
                time.sleep(1)
            self._answer(200, "audio/x-scpls", _playlist(icy.url("/mp3")))
        elif path.lstrip("/") in icy.streams:
            data, content_type = icy.streams[path.lstrip("/")]
            self._stream(data, content_type, lambda block: TITLE.encode())
        elif path == "/cp1250" and mp3:
            self._stream(mp3[0], mp3[1], lambda block: CP1250_TITLE.encode("cp1250"))
        elif path == "/changing" and mp3:
            # Each title is sent in two blocks in a row (a second of audio), then the other one.
            self._stream(mp3[0], mp3[1], lambda block: CHANGING_TITLES[block // 2 % 2].encode())
        elif path == "/once" and mp3:
            self._stream(mp3[0][:4 * METAINT], mp3[1], lambda block: TITLE.encode(), loop=False)
        else:
            self._answer(404, "text/plain", b"Not found")

    def _answer(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self, data: bytes, content_type: str, title, loop: bool = True) -> None:
        with_metadata = self.headers.get("Icy-MetaData", "").strip() == "1"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("icy-name", "Test Radio")
        if with_metadata:
            self.send_header("icy-metaint", str(METAINT))
        self.end_headers()
        position, block = 0, 0
        try:
            while loop or position < len(data):
                chunk = bytearray()
                while len(chunk) < METAINT and (loop or position < len(data)):
                    part = data[position:position + METAINT - len(chunk)]
                    chunk += part
                    position += len(part)
                    if loop:
                        position %= len(data)
                self.wfile.write(bytes(chunk) + (_metadata(title(block)) if with_metadata else b""))
                block += 1
        except OSError:   # the player hung up
            pass
