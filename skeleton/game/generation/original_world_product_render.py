"""Real render outputs from the playable world state, without any external assets.

Produces vector SVG for browser/desktop viewers and a P6 raster PPM for
offline native viewers. Images depict actual terrain cells, structures,
agents, player coordinates and persistent resource state, not decorative
stock imagery or hand-written fake preview screenshots.
"""
from __future__ import annotations
from html import escape
from .original_foundation_compiler import FoundationError
from .original_world_product_terrain import TerrainState, cell_at, validate_terrain
from .original_world_product_agents import PhysicalSociety, validate_society

COLORS = {
    "meadow": (119, 174, 92),
    "grove": (45, 111, 77),
    "stone": (121, 128, 141),
    "marsh": (72, 130, 156),
    "cliff": (61, 67, 79),
    "spring": (54, 155, 191),
    "sand": (213, 185, 118),
    "orchard": (158, 176, 82),
}
BUILDING_COLORS = {"hearth": "#ffb55f", "mill": "#e8d7a0", "beacon": "#f3e970"}


def scene(terrain: TerrainState, society: PhysicalSociety | None = None, *,
          radius: int = 10) -> dict:
    validate_terrain(terrain)
    if society is not None:
        validate_society(society, terrain)
    if type(radius) is not int or not 2 <= radius <= 24:
        raise FoundationError("render radius must be 2..24")
    ox, oy = terrain.position
    cells = tuple(
        cell_at(terrain, ox + dx, oy + dy)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
    )
    agents = tuple(
        {"id": p.id, "role": p.profession, "x": p.x, "y": p.y,
         "energy": p.energy, "health": p.health}
        for p in society.inhabitants
        if abs(p.x - ox) <= radius and abs(p.y - oy) <= radius
    ) if society is not None else ()
    return {
        "world": terrain.design_id, "biome": terrain.biome,
        "center": (ox, oy), "radius": radius, "side": radius * 2 + 1,
        "cells": cells, "people": agents, "player": terrain.position,
    }


def svg_render(terrain: TerrainState, society: PhysicalSociety | None = None, *,
               radius: int = 10, tile_size: int = 22, title: str = "Original World") -> str:
    if type(tile_size) is not int or not 8 <= tile_size <= 64:
        raise FoundationError("invalid render tile size")
    view = scene(terrain, society, radius=radius)
    side = view["side"]
    height = side * tile_size + 94
    width = side * tile_size
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">',
        f"<title>{escape(title)}</title>",
        f'<rect width="{width}" height="{height}" fill="#162025"/>',
    ]
    ox, oy = view["center"]
    for tile in view["cells"]:
        x = (tile.x - ox + radius) * tile_size
        y = (tile.y - oy + radius) * tile_size
        color = "#%02x%02x%02x" % COLORS[tile.kind]
        parts.append(f'<rect x="{x}" y="{y}" width="{tile_size}" height="{tile_size}" fill="{color}"/>')
        if tile.elevation > 3:
            parts.append(f'<path d="M{x} {y + tile_size} l{tile_size} {-tile_size}" '
                         f'stroke="#2b3442" stroke-width="1"/>')
        if tile.bridge:
            parts.append(f'<path d="M{x + 2} {y + tile_size // 2} h{tile_size - 4}" '
                         f'stroke="#e4be71" stroke-width="4"/>')
        if tile.building:
            parts.append(f'<rect x="{x + 5}" y="{y + 5}" width="{max(2,tile_size-10)}" '
                         f'height="{max(2,tile_size-10)}" fill="{BUILDING_COLORS[tile.building]}"/>')
    for p in view["people"]:
        px = (p["x"] - ox + radius) * tile_size + tile_size / 2
        py = (p["y"] - oy + radius) * tile_size + tile_size / 2
        parts.append(f'<circle cx="{px}" cy="{py}" r="{max(3,tile_size // 4)}" '
                     f'fill="#ffe6bf" stroke="#243044" stroke-width="1"/>')
    px = radius * tile_size + tile_size / 2
    py = radius * tile_size + tile_size / 2
    parts.append(f'<circle cx="{px}" cy="{py}" r="{max(4,tile_size // 3)}" '
                 f'fill="#69e5ee" stroke="#08354d" stroke-width="2"/>')
    parts.append(f'<rect x="0" y="{side * tile_size}" width="{width}" height="94" fill="#162025"/>')
    info = (
        f"{escape(title)} · {terrain.biome} · ({ox},{oy})",
        f"Energy {terrain.energy} · Provisions {terrain.provisions} · Water {terrain.freshwater}",
        f"Wood {terrain.lumber} · Stone {terrain.masonry} · "
        f"Residents {len(society.inhabitants) if society else 0} · Turn {terrain.turns}",
    )
    for i, value in enumerate(info):
        parts.append(f'<text x="9" y="{side * tile_size + 22 + 25*i}" '
                     f'fill="#eaf2f0" font-family="sans-serif" font-size="12">{value}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def ppm_render(terrain: TerrainState, society: PhysicalSociety | None = None, *,
               radius: int = 10, scale: int = 5) -> bytes:
    """Binary PPM: simple native raster image requiring no PIL, browser or GPU."""
    if type(scale) is not int or not 1 <= scale <= 12:
        raise FoundationError("render pixel scale outside safe bounds")
    view = scene(terrain, society, radius=radius)
    side = view["side"]
    width = height = side * scale
    positions = {(p["x"], p["y"]) for p in view["people"]}
    ox, oy = view["center"]
    raw = bytearray()
    for sy in range(height):
        dy = sy // scale - radius
        for sx in range(width):
            dx = sx // scale - radius
            cell = cell_at(terrain, ox + dx, oy + dy)
            rgb = COLORS[cell.kind]
            if cell.bridge:
                rgb = (218, 179, 101)
            if cell.building:
                rgb = (238, 216, 163)
            if (ox + dx, oy + dy) in positions:
                rgb = (250, 231, 192)
            if dx == 0 and dy == 0:
                rgb = (110, 229, 236)
            raw.extend(rgb)
    return f"P6\n{width} {height}\n255\n".encode() + bytes(raw)


def ascii_render(terrain: TerrainState, society: PhysicalSociety | None = None, *,
                 radius: int = 8) -> str:
    view = scene(terrain, society, radius=radius)
    sprites = {
        "meadow": ".", "grove": "T", "stone": "s",
        "marsh": "~", "cliff": "#", "spring": "w",
        "sand": ":", "orchard": "o",
    }
    people = {(p["x"], p["y"]) for p in view["people"]}
    ox, oy = view["center"]
    rows = []
    for dy in range(-radius, radius + 1):
        row = []
        for dx in range(-radius, radius + 1):
            tile = cell_at(terrain, ox + dx, oy + dy)
            symbol = sprites[tile.kind]
            if tile.bridge:
                symbol = "="
            if tile.building:
                symbol = "H"
            if (ox + dx, oy + dy) in people:
                symbol = "n"
            if (dx, dy) == (0, 0):
                symbol = "@"
            row.append(symbol)
        rows.append("".join(row))
    return "\n".join(rows)
