"""The audio player: GStreamer's playbin behind the controller's Player protocol.

How the Player contract (controller.py) is kept:
- Every pipeline and every playlist download gets a generation number. play() and stop() start a new
  one: the old playbin's bus watch is removed and the playbin set to NULL (which also flushes its bus),
  and anything still on its way (a bus message, a playlist result queued with GLib.idle_add) checks
  its generation when it is delivered and is dropped.
- Callbacks only come from the main loop (the bus watch and idle callbacks), never from inside play(),
  stop() or set_volume(). Even a pipeline that fails at once reports it from an idle callback.
- The volume is kept here and given to every new playbin.
"""
from __future__ import annotations

import logging
import os
import threading
import urllib.error
from typing import Callable

# For ICY titles GStreamer tries UTF-8 first and then these encodings (Polish stations send Windows-1250).
os.environ.setdefault("GST_ICY_TAG_ENCODING", "WINDOWS-1250")

import gi  # noqa: E402

gi.require_version("Gst", "1.0")
gi.require_version("GstAudio", "1.0")
from gi.repository import GLib, Gst, GstAudio  # noqa: E402

from .. import APP_ID, APP_NAME  # noqa: E402
from ..controller import ErrorKind  # noqa: E402
from ..core.net import USER_AGENT, NetworkError, fetch_bytes  # noqa: E402
from .playlists import first_stream, is_hls, is_playlist_type, is_playlist_url  # noqa: E402

Gst.init(None)

log = logging.getLogger(__name__)

PLAYLIST_LIMIT = 256 * 1024
MAX_PLAYLISTS = 3                 # playlists followed for one play(): one may point at another
_PLAY_FLAG_AUDIO = 1 << 1         # GstPlayFlags: audio only (no video window for a stream with video)
_PLAY_FLAG_SOFT_VOLUME = 1 << 4
_ACCESS_DENIED = (401, 402, 403, 407)


def make_audio_sink() -> Gst.Element | None:
    """PulseAudio's sink (PipeWire serves it too), else PipeWire's, named for the volume mixer.
    None lets playbin choose."""
    for factory in ("pulsesink", "pipewiresink"):
        sink = Gst.ElementFactory.make(factory, None)
        if sink is None:
            continue
        sink.set_property("stream-properties", Gst.Structure.new_from_string(
            f'props, application.name=(string)"{APP_NAME}", application.icon_name=(string)"{APP_ID}",'
            ' media.role=(string)"music"'))
        if sink.find_property("client-name") is not None:
            sink.set_property("client-name", APP_NAME)
        return sink
    return None


def _http_status(structure: Gst.Structure | None) -> int:
    if structure is None:
        return 0
    found, status = structure.get_uint("http-status-code")
    return status if found else 0


def _header(headers: Gst.Structure | None, name: str) -> str | None:
    for i in range(headers.n_fields() if headers is not None else 0):
        field = headers.nth_field_name(i)
        if field.lower() == name:
            return headers.get_string(field)
    return None


def _matches(error: GLib.Error | None, domain, *codes) -> bool:
    return error is not None and any(error.matches(domain.quark(), code) for code in codes)


class GstPlayer:
    def __init__(self, on_started: Callable[[], None], on_title: Callable[[str], None],
                 on_error: Callable[[ErrorKind, str], None], on_eos: Callable[[], None],
                 audio_sink_factory: Callable[[], Gst.Element | None] = make_audio_sink,
                 _: Callable[[str], str] = lambda s: s) -> None:
        self._on_started = on_started
        self._on_title = on_title
        self._on_error = on_error
        self._on_eos = on_eos
        self._make_sink = audio_sink_factory
        self._ = _
        self._volume = 100
        self._generation = 0
        self._playbin: Gst.Element | None = None
        self._source: Gst.Element | None = None
        self._url = ""
        # For one play(), across the pipelines and playlists it goes through:
        self._playlists = 0
        self._started = False
        self._title: str | None = None
        # For the current pipeline:
        self._http_status = 0
        self._buffering = False
        self._live = False

    # ---- Player ----

    def play(self, url: str) -> None:
        self._close()
        self._playlists = 0
        self._started = False
        self._title = None
        self._open(url)

    def stop(self) -> None:
        self._close()

    def set_volume(self, percent: int) -> None:
        self._volume = max(0, min(100, int(percent)))
        if self._playbin is not None:
            self._playbin.set_property("volume", self._linear_volume())

    # ---- Pipelines ----

    def _linear_volume(self) -> float:
        # A cubic slider, so it feels like Windows' (half way is quiet, not nearly full).
        return GstAudio.StreamVolume.convert_volume(
            GstAudio.StreamVolumeFormat.CUBIC, GstAudio.StreamVolumeFormat.LINEAR, self._volume / 100)

    def _close(self) -> None:
        """Ends the current pipeline or playlist download: nothing from it reaches the callbacks again."""
        self._generation += 1
        playbin, self._playbin, self._source = self._playbin, None, None
        if playbin is not None:
            playbin.get_bus().remove_watch()
            playbin.set_state(Gst.State.NULL)

    def _open(self, url: str) -> None:
        if is_playlist_url(url) and self._playlists < MAX_PLAYLISTS:
            self._download_playlist(url)
        else:
            self._start(url, sniff=True)

    def _start(self, url: str, sniff: bool) -> None:
        """A playbin for `url`. With `sniff`, a playlist Content-Type sends it to _download_playlist."""
        generation = self._generation
        self._url = url
        self._http_status = 0
        self._buffering = False
        playbin = Gst.ElementFactory.make("playbin", None)
        if playbin is None:
            self._fail_later(generation, *self._failure(None, 0))
            return
        playbin.set_property("uri", url)
        playbin.set_property("flags", _PLAY_FLAG_AUDIO | _PLAY_FLAG_SOFT_VOLUME)
        sink = self._make_sink()
        if sink is not None:
            playbin.set_property("audio-sink", sink)
        playbin.set_property("volume", self._linear_volume())
        playbin.connect("source-setup", self._on_source_setup, generation)
        playbin.get_bus().add_watch(GLib.PRIORITY_DEFAULT, self._on_message, generation, sniff)
        self._playbin = playbin
        result = playbin.set_state(Gst.State.PLAYING)
        self._live = result == Gst.StateChangeReturn.NO_PREROLL
        if result == Gst.StateChangeReturn.FAILURE:
            # Usually an ERROR on the bus says more and comes first; this is the fallback.
            self._fail_later(generation, *self._failure(None, 0))

    def _fail_later(self, generation: int, kind: ErrorKind, detail: str) -> None:
        def deliver() -> bool:
            if generation == self._generation:
                self._close()
                self._on_error(kind, detail)
            return False

        GLib.idle_add(deliver)

    def _on_source_setup(self, _playbin: Gst.Element, source: Gst.Element, generation: int) -> None:
        if generation != self._generation:
            return
        self._source = source
        if source.find_property("user-agent") is not None:
            source.set_property("user-agent", USER_AGENT)

    def _on_message(self, _bus: Gst.Bus, message: Gst.Message, generation: int, sniff: bool) -> bool:
        if generation != self._generation:
            return False            # an earlier pipeline's: drop it, and the watch with it
        kind = message.type
        if kind == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            log.warning("Playback failed in %s: %s (%s)", message.src.get_name(), error.message, debug)
            failure = self._failure(error, _http_status(message.parse_error_details()) or self._http_status)
            self._close()
            self._on_error(*failure)
        elif kind == Gst.MessageType.EOS:
            self._close()
            self._on_eos()
        elif kind == Gst.MessageType.STATE_CHANGED and message.src == self._playbin:
            _old, new, _pending = message.parse_state_changed()
            if new == Gst.State.PLAYING and not self._started:
                self._started = True
                self._on_started()
        elif kind == Gst.MessageType.TAG:
            found, title = message.parse_tag().get_string(Gst.TAG_TITLE)
            if found and title and title != self._title:
                self._title = title
                self._on_title(title)
        elif kind == Gst.MessageType.BUFFERING and not self._live:
            # Wait for the buffer to fill before playing, rather than stutter on a slow connection.
            percent = message.parse_buffering()
            if percent < 100 and not self._buffering:
                self._buffering = True
                self._playbin.set_state(Gst.State.PAUSED)
            elif percent >= 100 and self._buffering:
                self._buffering = False
                self._playbin.set_state(Gst.State.PLAYING)
        elif kind == Gst.MessageType.CLOCK_LOST:
            self._playbin.set_state(Gst.State.PAUSED)
            self._playbin.set_state(Gst.State.PLAYING)
        elif kind == Gst.MessageType.ELEMENT and message.src == self._source:
            self._on_http_headers(message.get_structure(), sniff)
        return True

    def _on_http_headers(self, structure: Gst.Structure | None, sniff: bool) -> None:
        """souphttpsrc's "http-headers": the HTTP status, and a playlist served under any name."""
        if structure is None or structure.get_name() != "http-headers":
            return
        self._http_status = _http_status(structure)
        if (sniff and self._playlists < MAX_PLAYLISTS and 200 <= self._http_status < 300
                and is_playlist_type(_header(structure.get_value("response-headers"), "content-type"))):
            url = self._url
            self._close()
            self._download_playlist(url)

    # ---- Playlists ----

    def _download_playlist(self, url: str) -> None:
        self._playlists += 1
        self._url = url
        generation = self._generation

        def work() -> None:
            try:
                data, error = fetch_bytes(url, limit=PLAYLIST_LIMIT), None
            except NetworkError as failure:
                data, error = None, failure
            GLib.idle_add(self._playlist_arrived, generation, url, data, error)

        threading.Thread(target=work, name="playlist", daemon=True).start()

    def _playlist_arrived(self, generation: int, url: str, data: bytes | None,
                          error: NetworkError | None) -> bool:
        if generation != self._generation:
            return False            # stopped, or another station, since the download began
        if error is not None:
            cause = error.__cause__
            status = cause.code if isinstance(cause, urllib.error.HTTPError) else 0
            failure = self._failure(None, status)
            self._close()
            self._on_error(*failure)
            return False
        text = data.decode("utf-8", errors="replace")
        if is_hls(text):
            self._start(url, sniff=False)
            return False
        stream = first_stream(text, url)
        if stream is None:
            self._close()
            self._on_error(ErrorKind.UNSUPPORTED, self._("This station uses a format that can't be played."))
        else:
            self._open(stream)
        return False

    # ---- Errors ----

    def _failure(self, error: GLib.Error | None, status: int) -> tuple[ErrorKind, str]:
        """What the controller needs to know about a failure, and what the user is told.
        `status` is the HTTP status, 0 if none (libsoup 2 gives DNS and connection failures codes below 100)."""
        _ = self._
        if 400 <= status < 500:
            text = (_("The station's server refused access ({code}).") if status in _ACCESS_DENIED
                    else _("The station's server returned error {code}."))
            return ErrorKind.REFUSED, text.format(code=status)
        if not 0 < status < 100 and _matches(error, Gst.ResourceError, Gst.ResourceError.NOT_AUTHORIZED,
                                             Gst.ResourceError.NOT_FOUND):
            return ErrorKind.REFUSED, _("The station's server refused access.")
        if (_matches(error, Gst.CoreError, Gst.CoreError.MISSING_PLUGIN)
                or _matches(error, Gst.StreamError, Gst.StreamError.CODEC_NOT_FOUND)):
            return ErrorKind.UNSUPPORTED, _("This station uses a format that can't be played.")
        if status >= 300:
            return ErrorKind.NETWORK, _("The station's server returned error {code}.").format(code=status)
        if self._started:
            return ErrorKind.NETWORK, _("The connection to the station was lost.")
        return ErrorKind.NETWORK, _("Couldn't connect to the station. Check your internet connection.")
