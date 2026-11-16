"""Pictures from bytes, made small: station logos, and the cover in the footer and the notification.

Nothing is decoded before its declared size is read from its header (core/imagesize.py): a picture wider or taller
than 4096 pixels, or in a format whose size isn't read there (SVG, TIFF…), is not a picture here. PNG and JPEG go
through GTK's own decoders. The others (ICO, GIF, WebP, BMP) go through gdk-pixbuf, whose decoders may run as
helper processes (glycin) that can fail to start in the Flatpak sandbox, so the common formats don't depend on
them. Safe to call from a worker thread.
"""
from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib  # noqa: E402

from .core.imagesize import fits  # noqa: E402

_GTK_FORMATS = (b"\x89PNG", b"\xff\xd8\xff")


def _texture(pixbuf: GdkPixbuf.Pixbuf) -> Gdk.Texture:
    memory_format = Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
    return Gdk.MemoryTexture.new(pixbuf.get_width(), pixbuf.get_height(), memory_format,
                                 pixbuf.read_pixel_bytes(), pixbuf.get_rowstride())


def _with_gtk(data: bytes, pixels: int) -> Gdk.Texture | None:
    try:
        texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
    except GLib.Error:
        return None
    width, height = texture.get_width(), texture.get_height()
    if max(width, height) <= pixels:
        return texture
    downloader = Gdk.TextureDownloader.new(texture)
    downloader.set_format(Gdk.MemoryFormat.R8G8B8A8)   # what a pixbuf holds: RGBA, not premultiplied
    raw, stride = downloader.download_bytes()
    pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(raw, GdkPixbuf.Colorspace.RGB, True, 8, width, height, stride)
    scale = pixels / max(width, height)
    small = pixbuf.scale_simple(max(1, round(width * scale)), max(1, round(height * scale)),
                                GdkPixbuf.InterpType.BILINEAR)
    return _texture(small) if small is not None else None


def _with_pixbuf(data: bytes, pixels: int) -> Gdk.Texture | None:
    try:
        stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, pixels, pixels, True, None)
    except GLib.Error:
        return None
    return _texture(pixbuf)


def picture(data: bytes, pixels: int) -> Gdk.Texture | None:
    """At most `pixels` on its longer side (a smaller picture keeps its size); None if it isn't a picture, or one
    too big to decode."""
    if not fits(data):
        return None
    first, second = (_with_gtk, _with_pixbuf) if data.startswith(_GTK_FORMATS) else (_with_pixbuf, _with_gtk)
    return first(data, pixels) or second(data, pixels)
