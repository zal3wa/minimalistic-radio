#!/usr/bin/env python3
"""Keeps only what the staged GStreamer plugins load; deletes everything else the packages brought.

Usage: prune.py INSTALL_DIR PLATFORM_DIR ARCH_TRIPLET PLUGIN...

A plugin the GNOME platform (PLATFORM_DIR, the content snap) already has is dropped. A kept plugin keeps the
libraries it links to, transitively, except those the platform has (they come from there at run time, as
libc comes from the base). Libraries are matched by soname in the folders the snap's LD_LIBRARY_PATH covers.
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

PT_LOAD, PT_DYNAMIC = 1, 2
DT_NULL, DT_NEEDED, DT_STRTAB = 0, 1, 5


def needed(path: Path) -> list[str]:
    """DT_NEEDED of an ELF file ([] when it isn't one, or is static)."""
    data = path.read_bytes()
    if data[:4] != b"\x7fELF":
        return []
    is64, endian = data[4] == 2, "<" if data[5] == 1 else ">"
    if is64:
        (phoff,), (phentsize, phnum) = struct.unpack_from(endian + "Q", data, 0x20), \
            struct.unpack_from(endian + "HH", data, 0x36)
    else:
        (phoff,), (phentsize, phnum) = struct.unpack_from(endian + "I", data, 0x1C), \
            struct.unpack_from(endian + "HH", data, 0x2A)
    loads, dynamic = [], None
    for i in range(phnum):
        offset = phoff + i * phentsize
        if is64:
            p_type, _, p_offset, p_vaddr, _, p_filesz, _, _ = struct.unpack_from(endian + "IIQQQQQQ", data, offset)
        else:
            p_type, p_offset, p_vaddr, _, p_filesz, _, _, _ = struct.unpack_from(endian + "IIIIIIII", data, offset)
        if p_type == PT_LOAD:
            loads.append((p_vaddr, p_offset, p_filesz))
        elif p_type == PT_DYNAMIC:
            dynamic = (p_offset, p_filesz)
    if dynamic is None:
        return []
    entry = endian + ("qQ" if is64 else "iI")
    tags, strtab = [], None
    for offset in range(dynamic[0], dynamic[0] + dynamic[1], struct.calcsize(entry)):
        tag, value = struct.unpack_from(entry, data, offset)
        if tag == DT_NULL:
            break
        if tag == DT_STRTAB:
            strtab = value
        tags.append((tag, value))
    base = next((strtab - v + o for v, o, size in loads if v <= strtab < v + size), strtab)

    def string(offset: int) -> str:
        start = base + offset
        return data[start:data.index(b"\0", start)].decode()

    return [string(value) for tag, value in tags if tag == DT_NEEDED]


def main(install: Path, platform: Path, triplet: str, plugins: list[str]) -> int:
    libdirs = [f"usr/lib/{triplet}", f"lib/{triplet}", "usr/lib", "lib"]
    platform_libdirs = libdirs + [f"usr/lib/{triplet}/pulseaudio"]   # desktop-launch adds that one too
    plugin_dir = Path("usr/lib", triplet, "gstreamer-1.0")

    def find(root: Path, dirs: list[str], soname: str) -> Path | None:
        return next((root / d / soname for d in dirs if os.path.lexists(root / d / soname)), None)

    keep: set[Path] = set()
    queue: list[Path] = []
    for name in plugins:
        if (platform / plugin_dir / name).exists():
            print(f"{name}: the GNOME platform has it")
        elif (install / plugin_dir / name).exists():
            print(f"{name}: kept")
            queue.append(install / plugin_dir / name)
        else:
            print(f"{name}: not in the staged packages")
            return 1
    while queue:
        path = queue.pop()
        if path in keep:
            continue
        while path.is_symlink():   # libfoo.so.1 -> libfoo.so.1.2.3, kept link by link
            keep.add(path)
            target = os.readlink(path)
            path = install / target.lstrip("/") if os.path.isabs(target) else path.parent / target
        real = path.resolve()
        keep.add(real)
        for soname in needed(real):
            if find(platform, platform_libdirs, soname):
                continue
            mine = find(install, libdirs, soname)
            if mine is not None:
                queue.append(mine)
            else:
                print(f"  {soname} (for {real.name}): neither staged nor the platform's: the base's or the GPU snap's")

    kept_bytes = removed_bytes = 0
    for path in sorted(install.rglob("*"), reverse=True):   # files before their folders
        if not path.is_symlink() and path.is_dir():
            if not any(path.iterdir()):
                path.rmdir()
            continue
        size = 0 if path.is_symlink() else path.stat().st_size
        if path in keep:
            kept_bytes += size
            if not path.is_symlink():
                print(f"  kept {size / 1e6:6.2f} MB  {path.relative_to(install)}")
        else:
            removed_bytes += size
            path.unlink()
    print(f"kept {kept_bytes / 1e6:.1f} MB, removed {removed_bytes / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]), sys.argv[3], sys.argv[4:]))
