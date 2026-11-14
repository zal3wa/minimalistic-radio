"""Drag to reorder: the arithmetic, without GTK (docs/superpowers/specs/2026-11-14-drag-to-reorder-design.md)."""
from __future__ import annotations

from typing import Sequence

HOLD_MS = 250          # held this long without moving, a station lifts
SLIDE_MS = 150         # the other stations slide apart this fast
SCROLL_EDGE = 48       # px from the top or bottom of the visible list where it starts scrolling by itself
SCROLL_STEP = 14       # px per tick at the very edge


def drop_index(centers: Sequence[float], origin: int, y: float) -> int:
    """Where the dragged row lands: one place down for every other row whose centre it has passed.

    `centers` are the rows' vertical centres before the drag, `origin` is the dragged row's index and
    `y` its centre now. Reaching a centre isn't passing it (in either direction), so the gap moves once
    the row is past halfway.
    """
    return sum(1 for i, center in enumerate(centers)
               if i != origin and (center < y or (center == y and i < origin)))


def gap_offsets(count: int, origin: int, target: int, height: float) -> list[float]:
    """How far each row is shifted so that a gap of `height` opens at `target` and closes at `origin`."""
    offsets = [0.0] * count
    if target > origin:
        for i in range(origin + 1, target + 1):
            offsets[i] = -height
    else:
        for i in range(target, origin):
            offsets[i] = height
    return offsets


def scroll_step(y: float, height: float) -> float:
    """How far the list scrolls per tick with the pointer at `y` in a visible area `height` tall:
    nothing away from the edges, faster the closer the pointer is to one (or past it)."""
    edge = min(SCROLL_EDGE, height / 4)
    if edge <= 0:
        return 0.0
    if y < edge:
        return -SCROLL_STEP * min(1.0, (edge - y) / edge)
    if y > height - edge:
        return SCROLL_STEP * min(1.0, (y - (height - edge)) / edge)
    return 0.0
