"""A picture's width and height as its file declares them, read before anything decodes it.

A downloaded picture (a logo, a favicon, a cover, stream artwork) of a few kilobytes can declare 50 000 × 50 000
pixels, which a decoder would try to hold in memory. Pictures wider or taller than MAX_SIDE are refused as if they
had failed to load, and so are formats whose size isn't read here (the same limit on Windows and macOS).

Read here: PNG, JPEG, GIF (every frame), WebP (VP8, VP8L, VP8X), BMP and ICO/CUR (every picture inside). This is a
header parser rather than gdk-pixbuf's size-prepared signal: in the Flatpak sandbox gdk-pixbuf's decoders may not
start at all (see pictures.py).
"""
from __future__ import annotations

MAX_SIDE = 4096

Size = tuple[int, int]

# Start of frame: every SOFn except DHT (C4), JPG (C8) and DAC (CC).
_SOF = frozenset((0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF))
_NO_LENGTH = frozenset((0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8))


def fits(data: bytes, limit: int = MAX_SIDE) -> bool:
    """Whether the picture may be decoded: its size is known, and neither side is 0 or more than `limit`."""
    size = picture_size(data)
    return size is not None and 0 < size[0] <= limit and 0 < size[1] <= limit


def picture_size(data: bytes) -> Size | None:
    """(width, height); None for a format not read here or a damaged header."""
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return _png(data, 0)
        if data.startswith(b"\xff\xd8"):
            return _jpeg(data)
        if data.startswith((b"GIF87a", b"GIF89a")):
            return _gif(data)
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return _webp(data)
        if data.startswith(b"BM"):
            return _dib(data, 14, icon=False)
        if data[:4] in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00"):
            return _ico(data)
    except (IndexError, ValueError):
        pass
    return None


def _u16(data: bytes, at: int, order: str = "little") -> int:
    if at + 2 > len(data):
        raise IndexError(at)
    return int.from_bytes(data[at:at + 2], order)


def _u32(data: bytes, at: int, order: str = "little", signed: bool = False) -> int:
    if at + 4 > len(data):
        raise IndexError(at)
    return int.from_bytes(data[at:at + 4], order, signed=signed)


def _png(data: bytes, at: int) -> Size | None:
    if data[at + 12:at + 16] != b"IHDR":
        return None
    return _u32(data, at + 16, "big"), _u32(data, at + 20, "big")


def _jpeg(data: bytes) -> Size | None:
    """The first frame header (SOFn), walking the segments before it."""
    at = 2
    while True:
        if data[at] != 0xFF:
            return None
        while data[at] == 0xFF:   # fill bytes
            at += 1
        marker = data[at]
        at += 1
        if marker in _NO_LENGTH:
            continue
        if marker in (0xD9, 0xDA):   # the end, or the picture data, before any frame
            return None
        length = _u16(data, at, "big")
        if marker in _SOF:
            return _u16(data, at + 5, "big"), _u16(data, at + 3, "big")
        if length < 2:
            return None
        at += length


def _gif(data: bytes) -> Size:
    """The logical screen, or more if a frame reaches beyond it."""
    width, height = _u16(data, 6), _u16(data, 8)
    at = 13
    if data[10] & 0x80:
        at += 3 << ((data[10] & 0x07) + 1)   # the global colour table
    while at < len(data):
        block = data[at]
        if block == 0x3B:   # the end
            break
        if block == 0x21:   # an extension: its label, then sub-blocks
            at = _sub_blocks(data, at + 2)
        elif block == 0x2C:   # a frame
            left, top, w, h = (_u16(data, at + n) for n in (1, 3, 5, 7))
            width, height = max(width, left + w), max(height, top + h)
            flags = data[at + 9]
            at += 10
            if flags & 0x80:
                at += 3 << ((flags & 0x07) + 1)   # its own colour table
            at = _sub_blocks(data, at + 1)        # after the LZW code size
        else:
            break   # not GIF any more: the decoder stops here too
    return width, height


def _sub_blocks(data: bytes, at: int) -> int:
    while True:
        size = data[at]
        at += 1 + size
        if size == 0:
            return at


def _webp(data: bytes) -> Size | None:
    chunk = data[12:16]
    if chunk == b"VP8 ":
        if data[23:26] != b"\x9d\x01\x2a":
            return None
        return _u16(data, 26) & 0x3FFF, _u16(data, 28) & 0x3FFF
    if chunk == b"VP8L":
        if data[20] != 0x2F:
            return None
        bits = _u32(data, 21)
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":
        if len(data) < 30:
            return None
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    return None


def _dib(data: bytes, at: int, icon: bool) -> Size:
    """A BMP's info header at `at` (in an icon, without the file header and with the height counted twice)."""
    header = _u32(data, at)
    if header == 12:   # OS/2
        width, height = _u16(data, at + 4), _u16(data, at + 6)
    else:
        width, height = _u32(data, at + 4, signed=True), _u32(data, at + 8, signed=True)
    height = abs(height)   # negative: stored top-down
    return abs(width), (height // 2 if icon else height)


def _ico(data: bytes) -> Size | None:
    """The largest of the pictures inside, as each declares itself (not as the directory says)."""
    count = _u16(data, 4)
    if count == 0:
        return None
    width = height = 0
    for entry in range(6, 6 + 16 * count, 16):
        size, offset = _u32(data, entry + 8), _u32(data, entry + 12)
        if size < 16 or offset + size > len(data):
            return None
        if data.startswith(b"\x89PNG\r\n\x1a\n", offset):
            found = _png(data, offset)
        else:
            found = _dib(data, offset, icon=True)
        if found is None:
            return None
        width, height = max(width, found[0]), max(height, found[1])
    return width, height
