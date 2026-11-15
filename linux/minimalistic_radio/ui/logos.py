"""Station logos: downloaded once into the cache folder, decoded off the main thread, kept in memory.

Keeping the decoded pictures means the list can be redrawn (a station added, moved or renamed)
without a logo going blank for a moment.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib  # noqa: E402

from ..core import net  # noqa: E402
from ..core.streams import is_web_url  # noqa: E402

LOGO_LIMIT = 2_000_000    # bytes downloaded at most
LOGO_PIXELS = 96          # decoded at most this big: shown at 40 px, sharp at 2× scaling
RETRY_SECONDS = 300       # a logo that couldn't be downloaded is tried again after this
_WORKERS = threading.BoundedSemaphore(4)

Texture = Gdk.Texture


def _decode(data: bytes) -> Texture | None:
    """A texture from PNG, JPEG, SVG… bytes, scaled down to LOGO_PIXELS; None if it isn't a picture."""
    try:
        stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, LOGO_PIXELS, LOGO_PIXELS, True, None)
    except GLib.Error:
        return None
    memory_format = Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
    return Gdk.MemoryTexture.new(pixbuf.get_width(), pixbuf.get_height(), memory_format,
                                 pixbuf.read_pixel_bytes(), pixbuf.get_rowstride())


def _save(path: Path, data: bytes) -> None:
    """Writes the file whole (a temporary file renamed into place) or not at all."""
    temp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".part")
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        os.replace(temp, path)
        temp = None
    except OSError:
        pass
    finally:
        if temp is not None:
            try:
                os.remove(temp)
            except OSError:
                pass


class LogoCache:
    """Used on the main loop only; the downloads and decoding run in worker threads."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._textures: dict[str, Texture | None] = {}
        self._failed: dict[str, float] = {}           # url → when the download failed
        self._waiting: dict[str, list[Callable[[Texture | None], None]]] = {}

    def lookup(self, url: str | None) -> tuple[bool, Texture | None]:
        """(known, texture). Known with None: there is no logo to show (none, not a web address, not a picture)."""
        if not is_web_url(url):
            return True, None
        if url in self._textures:
            return True, self._textures[url]
        failed = self._failed.get(url)
        if failed is not None and time.monotonic() - failed < RETRY_SECONDS:
            return True, None
        return False, None

    def load(self, url: str, callback: Callable[[Texture | None], None]) -> None:
        """Fetches a logo that lookup() doesn't know yet; calls back on the main loop.

        Only http and https addresses are fetched: anything else calls back with None at once."""
        if not is_web_url(url):
            callback(None)
            return
        waiting = self._waiting.get(url)
        if waiting is not None:
            waiting.append(callback)
            return
        self._waiting[url] = [callback]
        threading.Thread(target=self._work, args=(url, self._file(url)), daemon=True).start()

    def _file(self, url: str) -> Path:
        return self.folder / hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _work(self, url: str, path: Path) -> None:
        with _WORKERS:
            texture, downloaded = self._read(url, path)
        GLib.idle_add(self._deliver, url, texture, downloaded)

    @staticmethod
    def _read(url: str, path: Path) -> tuple[Texture | None, bool]:
        """(texture, whether the download worked). The cached file first, then the network."""
        try:
            texture = _decode(path.read_bytes())
            if texture is not None:
                return texture, True
        except OSError:
            pass
        try:
            data = net.fetch_bytes(url, 10, LOGO_LIMIT)   # load() let only http and https through
        except net.NetworkError:
            return None, False
        texture = _decode(data)
        if texture is not None:
            _save(path, data)
        return texture, True

    def _deliver(self, url: str, texture: Texture | None, downloaded: bool) -> bool:
        if downloaded:
            self._textures[url] = texture
            self._failed.pop(url, None)
        else:
            self._failed[url] = time.monotonic()
        for callback in self._waiting.pop(url, []):
            callback(texture)
        return GLib.SOURCE_REMOVE
