"""Tile line-of-sight on a room layout. Bresenham. Blocked by lock sockets."""

from __future__ import annotations

from typing import Any, Iterable


class LosError(ValueError):
    """Line-of-sight contract violation."""


def bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        cells.append((x, y))
        if x == x1 and y == y1:
            break
        twice = 2 * err
        if twice >= dy:
            err += dy
            x += sx
        if twice <= dx:
            err += dx
            y += sy
        if len(cells) > 256:
            raise LosError("ray too long")
    return cells


def blockers(room: dict[str, Any]) -> set[tuple[int, int]]:
    blocked: set[tuple[int, int]] = set()
    if room.get("kind") == "lock":
        blocked.add((int(room["w"]) // 2, int(room["h"]) // 2))
    for pile in room.get("scrap") or []:
        blocked.add((int(pile["x"]), int(pile["y"])))
    return blocked


def visible(room: dict[str, Any], src: tuple[int, int], dst: tuple[int, int]) -> bool:
    width, height = int(room["w"]), int(room["h"])
    for point in (src, dst):
        if not (0 <= point[0] <= width and 0 <= point[1] <= height):
            raise LosError("point outside room")
    wall = blockers(room)
    ray = bresenham(src[0], src[1], dst[0], dst[1])
    for cell in ray[1:-1]:
        if cell in wall:
            return False
    return True


def scan(room: dict[str, Any], origin: tuple[int, int], targets: Iterable[tuple[int, int]]) -> dict[str, Any]:
    hits = [list(target) for target in targets if visible(room, origin, target)]
    return {
        "kind": "los_scan",
        "origin": list(origin),
        "hits": hits,
        "n": len(hits),
        "stored_prose": 0,
    }
