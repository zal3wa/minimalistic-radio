"""The declared size of a picture, read before it is decoded (core/imagesize.py): tiny made-up headers."""
import pytest

from minimalistic_radio.core.imagesize import MAX_SIDE, fits, picture_size


def png(width, height):
    return (b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + width.to_bytes(4, "big")
            + height.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00" + b"\x00" * 4)


def jpeg(width, height, sof=0xC0, before=b""):
    app0 = b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    frame = (bytes([0xFF, sof]) + (17).to_bytes(2, "big") + b"\x08" + height.to_bytes(2, "big")
             + width.to_bytes(2, "big") + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01")
    return b"\xff\xd8" + app0 + before + frame + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + b"\x00" * 8 + b"\xff\xd9"


def gif(width, height, frames=()):
    data = b"GIF89a" + width.to_bytes(2, "little") + height.to_bytes(2, "little") + b"\x00\x00\x00"
    data += b"\x21\xf9\x04\x00\x00\x00\x00\x00"   # a graphic control extension
    for left, top, w, h in frames:
        data += (b"\x2c" + left.to_bytes(2, "little") + top.to_bytes(2, "little") + w.to_bytes(2, "little")
                 + h.to_bytes(2, "little") + b"\x00" + b"\x02\x02\x4c\x01\x00")
    return data + b"\x3b"


def webp(chunk, payload):
    body = b"WEBP" + chunk + len(payload).to_bytes(4, "little") + payload
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def vp8(width, height):
    return webp(b"VP8 ", b"\x30\x01\x00\x9d\x01\x2a" + width.to_bytes(2, "little") + height.to_bytes(2, "little")
                + b"\x00" * 10)


def vp8l(width, height):
    bits = (width - 1) | ((height - 1) << 14)
    return webp(b"VP8L", b"\x2f" + bits.to_bytes(4, "little") + b"\x00" * 8)


def vp8x(width, height):
    return webp(b"VP8X", b"\x10\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little"))


def bmp(width, height, header=40):
    if header == 12:
        dib = (12).to_bytes(4, "little") + width.to_bytes(2, "little") + height.to_bytes(2, "little") + b"\x01\x00\x18\x00"
    else:
        dib = (header.to_bytes(4, "little") + width.to_bytes(4, "little", signed=True)
               + height.to_bytes(4, "little", signed=True) + b"\x01\x00\x18\x00" + b"\x00" * (header - 16))
    return b"BM" + (14 + len(dib)).to_bytes(4, "little") + b"\x00" * 4 + (14 + len(dib)).to_bytes(4, "little") + dib


def ico(*images):
    """images: (directory width, directory height, embedded bytes)."""
    data = b"\x00\x00\x01\x00" + len(images).to_bytes(2, "little")
    offset = 6 + 16 * len(images)
    stored = b""
    for width, height, embedded in images:
        data += (bytes([width % 256, height % 256, 0, 0]) + b"\x01\x00\x20\x00" + len(embedded).to_bytes(4, "little")
                 + (offset + len(stored)).to_bytes(4, "little"))
        stored += embedded
    return data + stored


def dib(width, height):
    """A BMP inside an icon: no file header, the height counted twice (the picture and its mask)."""
    return (40).to_bytes(4, "little") + width.to_bytes(4, "little") + (2 * height).to_bytes(4, "little") + b"\x00" * 28


MAKERS = {"png": png, "jpeg": jpeg, "progressive jpeg": lambda w, h: jpeg(w, h, sof=0xC2), "gif": gif,
          "webp": vp8, "lossless webp": vp8l, "extended webp": vp8x, "bmp": bmp,
          "os/2 bmp": lambda w, h: bmp(w, h, header=12), "bmp v5": lambda w, h: bmp(w, h, header=124),
          "png icon": lambda w, h: ico((0, 0, png(w, h))), "bmp icon": lambda w, h: ico((0, 0, dib(w, h)))}


@pytest.mark.parametrize("kind", MAKERS)
def test_each_format_declares_its_size(kind):
    assert picture_size(MAKERS[kind](600, 300)) == (600, 300)


@pytest.mark.parametrize("kind", MAKERS)
def test_4096_pixels_on_a_side_is_the_most(kind):
    assert MAX_SIDE == 4096
    make = MAKERS[kind]
    assert fits(make(4096, 4096)) and fits(make(1, 1))
    assert not fits(make(4097, 16)) and not fits(make(16, 4097))


@pytest.mark.parametrize("data", [
    b"II*\x00\x08\x00\x00\x00" + b"\x00" * 32,                       # TIFF
    b"<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'/>",
    b"\x00\x00\x00\x1cftypavif" + b"\x00" * 32,                      # AVIF
    b"<html>not a picture</html>", b"", b"\x89PNG",
], ids=["tiff", "svg", "avif", "html", "nothing", "cut png"])
def test_a_format_whose_size_cant_be_read_is_refused(data):
    assert picture_size(data) is None and not fits(data)


def test_damaged_headers_are_refused():
    assert not fits(png(16, 16).replace(b"IHDR", b"IHDX"))
    assert not fits(jpeg(16, 16)[:20])                         # cut before the frame
    assert not fits(jpeg(16, 0))                               # a height given later (DNL): not known before
    assert not fits(b"\xff\xd8\xff\xda\x00\x02\xff\xd9")       # the picture data before any frame
    assert not fits(vp8(16, 16)[:26])
    assert not fits(ico())                                     # an icon without pictures
    assert not fits(ico((16, 16, png(16, 16)))[:30])           # its picture is missing


def test_jpeg_segments_before_the_frame_are_skipped():
    exif = b"\xff\xe1" + (8).to_bytes(2, "big") + b"Exif\x00\x00"
    padding = b"\xff\xff"   # fill bytes before a marker
    assert picture_size(jpeg(640, 480, before=exif + padding)) == (640, 480)
    assert picture_size(jpeg(640, 480, sof=0xC1)) == (640, 480)   # extended sequential


def test_a_top_down_bmp():
    assert picture_size(bmp(32, -20)) == (32, 20)


def test_a_gif_frame_bigger_than_its_screen_counts():
    assert picture_size(gif(16, 16, [(0, 0, 16, 16)])) == (16, 16)
    assert picture_size(gif(16, 16, [(0, 0, 8, 8), (10, 2, 300, 20)])) == (310, 22)
    assert not fits(gif(16, 16, [(0, 0, 5000, 5000)]))


def test_every_picture_in_an_icon_counts():
    assert picture_size(ico((16, 16, png(16, 16)), (32, 32, dib(32, 32)))) == (32, 32)
    assert not fits(ico((16, 16, png(16, 16)), (16, 16, png(5000, 5000))))   # the directory says 16
    assert not fits(ico((16, 16, dib(16, 16)), (16, 16, dib(16, 5000))))
