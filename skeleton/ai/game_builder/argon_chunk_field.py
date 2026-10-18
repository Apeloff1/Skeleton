"""Argon chunk fields: closed character factors on a spatial design grid.

A field is a custom game-creation sheet. Skin, eyes, hair, clothing, items,
and a fixed set of coherence factors are named once and copied onto every
chunk. The coherence digest hashes those variables. It ignores how many chunks
the sheet was rasterized into, so a finer grid and a 2x2 merge of that grid
describe the same character.

``argon_tier_plan`` counts chunks for a ladder tier, including 64k, and does
not allocate the raster. Materialized fields stay on a small even grid.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from skeleton.developer.jeeves_game_scale_ladder import RESOLUTION_LADDER

SCHEMA = "skeleton.game.argon_chunk_field.v1"

NAMED_COLORS: dict[str, tuple[int, int, int, int]] = {
    "ink": (18, 16, 20, 255),
    "paper": (236, 228, 210, 255),
    "sand": (214, 176, 132, 255),
    "ochre": (176, 112, 64, 255),
    "umber": (92, 58, 40, 255),
    "clay": (168, 96, 72, 255),
    "rose": (196, 120, 128, 255),
    "olive": (96, 112, 64, 255),
    "moss": (64, 96, 72, 255),
    "sea": (48, 96, 128, 255),
    "slate": (72, 84, 96, 255),
    "ash": (128, 128, 132, 255),
    "ivory": (244, 236, 220, 255),
    "wine": (112, 40, 56, 255),
    "gold": (196, 160, 72, 255),
    "copper": (168, 104, 64, 255),
}

FACTORS: tuple[str, ...] = (
    "skin_tone",
    "eye_color",
    "hair_color",
    "hair_style",
    "brow",
    "lips",
    "clothing_primary",
    "clothing_secondary",
    "clothing_trim",
    "cloth",
    "leather",
    "metal",
    "wear",
    "item_kind",
    "item_color",
    "palette_name",
    "outline",
    "pattern",
    "accessory",
    "body_region",
)

COLOR_FACTORS = frozenset({
    "skin_tone",
    "eye_color",
    "hair_color",
    "brow",
    "lips",
    "clothing_primary",
    "clothing_secondary",
    "clothing_trim",
    "item_color",
    "outline",
})

HAIR_STYLES = frozenset({"cropped", "braid", "loose", "tied", "shaved", "hooded"})
CLOTH = frozenset({"linen", "wool", "silk", "canvas", "felt"})
LEATHER = frozenset({"none", "strap", "belt", "glove", "boot"})
METAL = frozenset({"none", "buckle", "ring", "clasp", "pin"})
WEAR = frozenset({"fresh", "worn", "mended", "faded", "weathered"})
ITEM_KINDS = frozenset({"none", "satchel", "lantern", "map", "key", "charm"})
PALETTES = frozenset({"field", "dusk", "harbor", "hearth"})
PATTERNS = frozenset({"plain", "stripe", "check", "hem", "speck"})
ACCESSORIES = frozenset({"none", "scarf", "band", "cloak-pin", "bead"})
BODY_REGIONS = frozenset({"head", "face", "torso", "limb", "hand"})

CLOSED_TEXT = {
    "hair_style": HAIR_STYLES,
    "cloth": CLOTH,
    "leather": LEATHER,
    "metal": METAL,
    "wear": WEAR,
    "item_kind": ITEM_KINDS,
    "palette_name": PALETTES,
    "pattern": PATTERNS,
    "accessory": ACCESSORIES,
    "body_region": BODY_REGIONS,
}

# Higher priority survives a 2x2 merge. Palette never beats a drawn feature.
ROLE_PRIORITY: tuple[str, ...] = (
    "eye",
    "hair",
    "skin",
    "clothing",
    "item",
    "outline",
    "palette",
)

MAX_MATERIAL_EDGE = 64
_MICRO = 4


class ArgonChunkError(ValueError):
    pass


def _require_even_edge(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArgonChunkError(f"{name} must be an integer")
    if value < minimum or value > MAX_MATERIAL_EDGE or value % 2 != 0:
        raise ArgonChunkError(
            f"{name} must be an even integer from {minimum} through {MAX_MATERIAL_EDGE}"
        )
    return value


def validate_variables(variables: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(variables, Mapping):
        raise ArgonChunkError("variables must be a mapping")
    if set(variables) != set(FACTORS):
        missing = [name for name in FACTORS if name not in variables]
        extra = sorted(set(variables) - set(FACTORS))
        raise ArgonChunkError(f"variables must match the closed factor set; missing={missing} extra={extra}")
    cleaned: dict[str, str] = {}
    for name in FACTORS:
        raw = variables[name]
        if not isinstance(raw, str) or raw != raw.strip() or not raw:
            raise ArgonChunkError(f"{name} must be a non-empty token")
        if name in COLOR_FACTORS:
            if raw not in NAMED_COLORS:
                raise ArgonChunkError(f"{name} uses an unknown color name")
        else:
            allowed = CLOSED_TEXT[name]
            if raw not in allowed:
                raise ArgonChunkError(f"{name} is outside the closed vocabulary")
        cleaned[name] = raw
    return cleaned


def coherence_digest(variables: Mapping[str, str]) -> str:
    """Hash the character sheet only. Resolution and chunk count are excluded."""
    payload = json.dumps(
        {name: variables[name] for name in FACTORS},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _role_at(x: int, y: int, chunks_x: int, chunks_y: int) -> str:
    if y == 0:
        return "hair"
    if y == 1:
        return "eye"
    if y == 2:
        return "skin"
    if y == chunks_y - 1:
        return "item"
    if x == 0 or x == chunks_x - 1:
        return "outline"
    return "clothing"


def _accent(variables: Mapping[str, str], role: str) -> str:
    if role == "hair":
        return variables["brow"]
    if role == "eye":
        return variables["brow"]
    if role == "skin":
        return variables["lips"]
    if role == "item":
        return variables["metal"] if variables["metal"] != "none" else variables["outline"]
    if role == "outline":
        return variables["outline"]
    return variables["clothing_trim"]


def _micro_pattern(role: str, variables: Mapping[str, str]) -> list[list[str]]:
    """4 by 4 named-color detail inside one chunk. Wear and pattern change it."""
    base = {
        "hair": variables["hair_color"],
        "eye": variables["eye_color"],
        "skin": variables["skin_tone"],
        "clothing": variables["clothing_primary"],
        "item": variables["item_color"],
        "outline": variables["outline"],
        "palette": variables["clothing_secondary"],
    }[role]
    accent = _accent(variables, role)
    if accent == "none":
        accent = variables["outline"]
    if accent not in NAMED_COLORS:
        accent = variables["outline"]
    grid = [[base for _ in range(_MICRO)] for _ in range(_MICRO)]
    pattern = variables["pattern"]
    if pattern == "stripe":
        for row in grid:
            row[1] = accent
            row[2] = accent
    elif pattern == "check":
        for y in range(_MICRO):
            for x in range(_MICRO):
                if (x + y) % 2 == 0:
                    grid[y][x] = accent
    elif pattern == "hem":
        grid[3] = [variables["clothing_trim"] for _ in range(_MICRO)]
    elif pattern == "speck":
        grid[1][2] = accent
        grid[2][1] = accent
    wear = variables["wear"]
    if wear in {"worn", "faded", "weathered"}:
        grid[0][0] = variables["outline"]
    elif wear == "mended":
        grid[3][3] = variables["clothing_trim"]
    if role == "eye":
        grid[0][1] = variables["brow"]
        grid[0][2] = variables["brow"]
        grid[1][1] = variables["eye_color"]
        grid[1][2] = variables["eye_color"]
    if role == "hair" and variables["hair_style"] in {"braid", "tied"}:
        grid[2][0] = variables["clothing_trim"]
        grid[3][0] = variables["clothing_trim"]
    if role == "item" and variables["item_kind"] != "none":
        grid[2][2] = variables["item_color"]
    for row in grid:
        for color in row:
            if color not in NAMED_COLORS:
                raise ArgonChunkError("micro pattern left the named palette")
    return grid


def _chunk(x: int, y: int, role: str, variables: dict[str, str]) -> dict[str, Any]:
    return {
        "x": x,
        "y": y,
        "role": role,
        "variables": dict(variables),
        "micro": _micro_pattern(role, variables),
    }


def build_argon_field(
    variables: Mapping[str, object],
    *,
    chunks_x: int,
    chunks_y: int,
) -> dict[str, Any]:
    """Materialize a small even grid. Row 0 hair, row 1 eyes, row 2 skin, last row items."""
    cleaned = validate_variables(variables)
    cx = _require_even_edge(chunks_x, "chunks_x", minimum=2)
    cy = _require_even_edge(chunks_y, "chunks_y", minimum=4)
    chunks = [
        _chunk(x, y, _role_at(x, y, cx, cy), cleaned)
        for y in range(cy)
        for x in range(cx)
    ]
    return {
        "schema": SCHEMA,
        "chunks_x": cx,
        "chunks_y": cy,
        "variables": cleaned,
        "chunks": chunks,
        "coherence_digest": coherence_digest(cleaned),
        "allocates_full_tier_buffer": False,
        "model_super_resolution": False,
    }


def downscale_argon(field: Mapping[str, Any]) -> dict[str, Any]:
    """Merge every 2 by 2 block. Field variables are copied, so no factor is dropped.

    The surviving role is the highest priority role in the block
    (eye, then hair, skin, clothing, item, outline, palette). Ties keep the
    upper-left chunk of that role. The coherence digest is unchanged.
    """
    if not isinstance(field, Mapping) or field.get("schema") != SCHEMA:
        raise ArgonChunkError("downscale requires an argon chunk field")
    variables = validate_variables(field.get("variables", {}))
    if coherence_digest(variables) != field.get("coherence_digest"):
        raise ArgonChunkError("field digest does not match its variables")
    cx = field.get("chunks_x")
    cy = field.get("chunks_y")
    if isinstance(cx, bool) or not isinstance(cx, int) or isinstance(cy, bool) or not isinstance(cy, int):
        raise ArgonChunkError("field dimensions must be integers")
    if cx % 2 or cy % 2 or cx < 2 or cy < 2:
        raise ArgonChunkError("argon downscale requires a positive even grid")
    chunks = field.get("chunks")
    if not isinstance(chunks, list) or len(chunks) != cx * cy:
        raise ArgonChunkError("chunk list does not match the field grid")
    by_pos = {(chunk["x"], chunk["y"]): chunk for chunk in chunks}
    if len(by_pos) != len(chunks):
        raise ArgonChunkError("duplicate chunk coordinates")
    rank = {role: index for index, role in enumerate(ROLE_PRIORITY)}
    merged = []
    for y in range(0, cy, 2):
        for x in range(0, cx, 2):
            block = [by_pos[(x + dx, y + dy)] for dy in (0, 1) for dx in (0, 1)]
            winner = min(block, key=lambda chunk: (rank[chunk["role"]], chunk["y"], chunk["x"]))
            merged.append({
                "x": x // 2,
                "y": y // 2,
                "role": winner["role"],
                "variables": dict(variables),
                "micro": [list(row) for row in winner["micro"]],
            })
    return {
        "schema": SCHEMA,
        "chunks_x": cx // 2,
        "chunks_y": cy // 2,
        "variables": dict(variables),
        "chunks": merged,
        "coherence_digest": coherence_digest(variables),
        "allocates_full_tier_buffer": False,
        "model_super_resolution": False,
    }


def argon_tier_plan(tier: int, *, chunk_edge: int = 32) -> dict[str, Any]:
    """Count chunks along a ladder tier. Does not allocate a raster."""
    if isinstance(tier, bool) or not isinstance(tier, int) or tier not in RESOLUTION_LADDER:
        raise ArgonChunkError("tier must be a resolution-ladder edge")
    if isinstance(chunk_edge, bool) or not isinstance(chunk_edge, int) or chunk_edge not in (8, 16, 32, 64):
        raise ArgonChunkError("chunk_edge must be 8, 16, 32, or 64")
    if tier % chunk_edge != 0:
        raise ArgonChunkError("chunk_edge must divide the tier")
    along = tier // chunk_edge
    return {
        "schema": SCHEMA,
        "tier": tier,
        "chunk_edge": chunk_edge,
        "chunks_along_edge": along,
        "chunk_count": along * along,
        "factor_count": len(FACTORS),
        "allocates_buffer": False,
        "allocates_full_tier_buffer": False,
        "model_super_resolution": False,
        "native_hardware_qualified": False,
    }


def raster_argon(field: Mapping[str, Any], *, chunk_edge: int = 8) -> tuple[bytes, int, int]:
    """Paint a small field. Each chunk repeats its 4 by 4 named-color micro pattern."""
    if not isinstance(field, Mapping) or field.get("schema") != SCHEMA:
        raise ArgonChunkError("raster requires an argon chunk field")
    if isinstance(chunk_edge, bool) or not isinstance(chunk_edge, int) or chunk_edge not in (4, 8, 16, 32):
        raise ArgonChunkError("raster chunk_edge must be 4, 8, 16, or 32")
    if chunk_edge % _MICRO != 0:
        raise ArgonChunkError("raster chunk_edge must be a multiple of 4")
    cx = field["chunks_x"]
    cy = field["chunks_y"]
    if not isinstance(cx, int) or not isinstance(cy, int):
        raise ArgonChunkError("field dimensions must be integers")
    width = cx * chunk_edge
    height = cy * chunk_edge
    if width * height > 1024 * 1024:
        raise ArgonChunkError("raster exceeds the bounded pixel budget")
    scale = chunk_edge // _MICRO
    out = bytearray(width * height * 4)
    for chunk in field["chunks"]:
        micro = chunk["micro"]
        origin_x = chunk["x"] * chunk_edge
        origin_y = chunk["y"] * chunk_edge
        for my in range(_MICRO):
            for mx in range(_MICRO):
                color = NAMED_COLORS[micro[my][mx]]
                for sy in range(scale):
                    for sx in range(scale):
                        px = origin_x + mx * scale + sx
                        py = origin_y + my * scale + sy
                        base = (py * width + px) * 4
                        out[base:base + 4] = bytes(color)
    return bytes(out), width, height
