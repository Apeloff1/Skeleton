"""Target-aware original console projects inside the canonical file manifest.

The backend owns durable revision/rights/CAS. This module builds and validates
inert candidate files; source is never executed here. Physical hardware facts
are explicit for known formats and remain unavailable for other targets.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType

from .game_console_assets import (
    ConsoleAssetError,
    IndexedImage,
    asset_receipt,
    color_hex,
    decode_palette,
    decode_pcm_wav,
    decode_png,
    decode_tiles,
    decode_tim,
    encode_palette,
    encode_tiles,
    encode_tim,
    image_to_tiles,
    nes_attribute_table,
    png_rgba,
    tile_codec_descriptor,
    tilemap_entry,
    transform_rgba,
    transform_tim,
)
from .game_console_graph import (
    GRAPH_PATH,
    ConsoleSceneGraph,
    SceneGraphError,
    empty_scene_graph,
)

PROJECT_SCHEMA = "skeleton.console_editor_project.v1"
PROJECT_PATH = "game/editor/console.json"
MAX_PROJECT_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_FILE_TOTAL = 7 * 1024 * 1024
MAX_FILES = 128
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ACTIONS = ("idle", "left", "right", "up", "down", "jump", "attack", "interact", "water", "plant", "fish")
_KINDS = {
    "player",
    "goal",
    "pickup",
    "hazard",
    "platform",
    "decoration",
    "crop",
    "npc",
    "water",
    "enemy",
    "portal",
}
_COLLISIONS = {"none", "solid", "one_way", "hazard", "goal", "water"}


class ConsoleEditorError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code, self.status_code = code, status_code


def _int(value: object, lower: int, upper: int, label: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ConsoleEditorError("editor_bounds", f"{label} must be an integer within [{lower},{upper}]")
    return value


def _number(value: object, lower: float, upper: float, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ConsoleEditorError("editor_bounds", f"{label} must be finite within [{lower},{upper}]")
    return float(value)


def _id(value: object, label: str = "identity") -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ConsoleEditorError("editor_identity", f"{label} requires a normalized bounded identifier")
    return value


def _json(value: object, maximum: int = MAX_PROJECT_BYTES) -> bytes:
    stack, nodes, estimated = [(value, 0)], 0, 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        estimated += 2
        if nodes > 500_000 or depth > 16 or estimated > maximum:
            raise ConsoleEditorError(
                "editor_payload_limit", "Editor JSON exceeds structural or byte capacity"
            )
        if isinstance(node, Mapping):
            if len(node) > 65536 or any(not isinstance(key, str) or len(key) > 128 for key in node):
                raise ConsoleEditorError("editor_payload_invalid", "Editor object keys are invalid")
            estimated += sum(len(key.encode()) + 3 for key in node)
            stack.extend((item, depth + 1) for item in node.values())
        elif isinstance(node, (list, tuple)):
            if len(node) > 65536:
                raise ConsoleEditorError("editor_payload_limit", "Editor sequence exceeds capacity")
            stack.extend((item, depth + 1) for item in node)
        elif isinstance(node, str):
            if len(node) > maximum:
                raise ConsoleEditorError("editor_payload_limit", "Editor text exceeds capacity")
            estimated += len(node.encode())
        elif node is None or type(node) is bool:
            estimated += 5
        elif type(node) is int:
            if abs(node) > 2**63 - 1:
                raise ConsoleEditorError("editor_payload_limit", "Editor integers exceed 64-bit capacity")
            estimated += 20
        elif type(node) is float and math.isfinite(node):
            estimated += 25
        else:
            raise ConsoleEditorError("editor_payload_invalid", "Editor accepts only finite JSON data")
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    if len(raw) > maximum:
        raise ConsoleEditorError("editor_payload_limit", "Editor JSON exceeds byte capacity")
    return raw


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value, 8 * 1024 * 1024)).hexdigest()


def _pairs(values: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in values:
        if key in result:
            raise ConsoleEditorError("editor_duplicate_key", "Editor JSON contains duplicate object keys")
        result[key] = value
    return result


def _load(raw: str, maximum: int = MAX_PROJECT_BYTES) -> dict:
    if not isinstance(raw, str) or len(raw) > maximum or len(raw.encode()) > maximum:
        raise ConsoleEditorError("editor_payload_limit", "Editor document bytes exceed capacity")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ConsoleEditorError("editor_payload_invalid", "Non-finite JSON is forbidden")
            ),
        )
    except (ValueError, RecursionError) as exc:
        raise ConsoleEditorError("editor_json_invalid", "Editor document is invalid bounded JSON") from exc
    _json(value, maximum)
    if not isinstance(value, dict):
        raise ConsoleEditorError("editor_document_invalid", "Editor document must be an object")
    return value


def _path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 240
        or "\\" in value
        or ":" in value
        or value.startswith("/")
        or any(part in ("", ".", "..") for part in value.split("/"))
        or any(ord(char) < 32 for char in value)
    ):
        raise ConsoleEditorError("editor_path_invalid", "Project paths require exact safe relative names")
    return value


def _files(values: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(values, Mapping) or len(values) > MAX_FILES:
        raise ConsoleEditorError("editor_file_limit", "Project file count exceeds editor capacity")
    result, total = {}, 0
    for path, text in values.items():
        path = _path(path)
        if not isinstance(text, str) or len(text.encode()) > (
            MAX_PROJECT_BYTES if path == PROJECT_PATH else MAX_FILE_BYTES
        ):
            raise ConsoleEditorError("editor_file_limit", "Project source file exceeds byte capacity")
        total += len(text.encode())
        if total > MAX_FILE_TOTAL:
            raise ConsoleEditorError("editor_file_limit", "Project source file aggregate exceeds capacity")
        result[path] = text
    return result


def file_manifest_digest(files: Mapping[str, str]) -> str:
    """Exactly matches the existing backend canonical JSON file-map identity."""
    return _digest(_files(files))


def _target_id(value: str) -> str:
    if not isinstance(value, str) or len(value) > 128:
        raise ConsoleEditorError("editor_target_unknown", "Target must name the canonical Dragon catalog")
    value = value.removeprefix("dragon_native:").removeprefix("emulator:")
    aliases = {
        "pc": "pc_linux",
        "gameboy": "game_boy",
        "gb": "game_boy",
        "gbc": "game_boy_color",
        "gba": "game_boy_advance",
        "sms": "master_system",
        "n64": "nintendo_64",
        "xbox": "xbox_original",
        "xbox360": "xbox_360",
        "dos_pc": "dos_vga",
    }
    return aliases.get(value, value)


def _catalog() -> tuple[dict, ...]:
    from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

    rows = target_catalog()
    if not isinstance(rows, tuple) or not 1 <= len(rows) <= 512:
        raise ConsoleEditorError("editor_catalog_invalid", "Canonical target catalog is unavailable")
    return rows


_NATIVE = {
    "nes": {
        "codec": "nes_2bpp",
        "palette_format": "nes_palette_indices",
        "palette_colors": 4,
        "palette_banks": 4,
        "tile_banks": 2,
        "tiles_per_bank": 256,
        "vram_bytes": 2048,
        "pattern_bytes": 8192,
        "rom_bank_bytes": 16384,
        "map_width": 32,
        "map_height": 30,
        "endianness": "little",
        "hardware_sprites": 64,
        "scope": "NROM CHR/PPU authoring; mapper-dependent cartridge RAM unavailable",
    },
    "game_boy": {
        "codec": "gb_2bpp",
        "palette_format": "dmg_gray",
        "palette_colors": 4,
        "palette_banks": 1,
        "tile_banks": 1,
        "tiles_per_bank": 256,
        "vram_bytes": 8192,
        "pattern_bytes": 6144,
        "rom_bank_bytes": 16384,
        "map_width": 32,
        "map_height": 32,
        "endianness": "little",
        "hardware_sprites": 40,
        "scope": "Unsigned BG tile indices; physical VRAM384tile slots includes signed addressing modes",
    },
    "game_boy_color": {
        "codec": "gb_2bpp",
        "palette_format": "gb_bgr555",
        "palette_colors": 4,
        "palette_banks": 8,
        "tile_banks": 2,
        "tiles_per_bank": 256,
        "vram_bytes": 16384,
        "pattern_bytes": 12288,
        "rom_bank_bytes": 16384,
        "map_width": 32,
        "map_height": 32,
        "endianness": "little",
        "hardware_sprites": 40,
        "scope": "Unsigned CGB BG index and separate bank/palette attribute plane",
    },
    "snes": {
        "codec": "snes_4bpp",
        "palette_format": "snes_bgr555",
        "palette_colors": 16,
        "palette_banks": 8,
        "tile_banks": 1,
        "tiles_per_bank": 1024,
        "vram_bytes": 65536,
        "pattern_bytes": 65536,
        "rom_bank_bytes": 32768,
        "map_width": 64,
        "map_height": 64,
        "endianness": "little",
        "hardware_sprites": 128,
        "scope": "Mode1 4bpp BG planes; LoROM authoring bank size, not cartridge mapper certification",
    },
    "genesis": {
        "codec": "genesis_4bpp",
        "palette_format": "genesis_bgr333",
        "palette_colors": 16,
        "palette_banks": 4,
        "tile_banks": 1,
        "tiles_per_bank": 2048,
        "vram_bytes": 65536,
        "pattern_bytes": 65536,
        "rom_bank_bytes": None,
        "map_width": 128,
        "map_height": 128,
        "endianness": "big",
        "hardware_sprites": 80,
        "scope": "H40 VDP pattern/name table; native plane dimension combinations validated separately",
    },
    "game_boy_advance": {
        "codec": "gba_4bpp",
        "codecs": ["gba_4bpp", "gba_8bpp"],
        "palette_format": "gba_bgr555",
        "palette_colors": 16,
        "palette_banks": 16,
        "tile_banks": 1,
        "tiles_per_bank": 1024,
        "vram_bytes": 98304,
        "pattern_bytes": 65536,
        "rom_bank_bytes": None,
        "map_width": 64,
        "map_height": 64,
        "endianness": "little",
        "hardware_sprites": 128,
        "scope": "Mode0 text BG; shared BG64KiB/OBJ32KiB capacity, not every GBA video mode",
    },
    "master_system": {
        "codec": "sms_4bpp",
        "palette_format": "sms_rgb222",
        "palette_colors": 16,
        "palette_banks": 2,
        "tile_banks": 1,
        "tiles_per_bank": 512,
        "vram_bytes": 16384,
        "pattern_bytes": 16384,
        "rom_bank_bytes": 16384,
        "map_width": 32,
        "map_height": 28,
        "endianness": "little",
        "hardware_sprites": 64,
        "scope": "Mode4 VDP name table and CRAM",
    },
    "ps1": {
        "codec": "indexed_8bpp",
        "palette_format": "ps1_bgr555",
        "palette_colors": 256,
        "palette_banks": 16,
        "tile_banks": 1,
        "tiles_per_bank": 2048,
        "vram_bytes": 1048576,
        "pattern_bytes": None,
        "rom_bank_bytes": None,
        "map_width": 256,
        "map_height": 256,
        "endianness": "little",
        "hardware_sprites": None,
        "scope": "TIM VRAM word geometry; GPU memory1MiB, no universal texture/tile scene layout",
    },
}


@dataclass(frozen=True, slots=True)
class ConsoleEditorProfile:
    target_id: str
    label: str
    _json: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self._json.encode()).hexdigest()

    def as_dict(self) -> dict:
        return {**json.loads(self._json), "profile_digest": self.digest}


def console_profile(target_id: str) -> ConsoleEditorProfile:
    key = _target_id(target_id)
    row = next((row for row in _catalog() if row["id"] == key), None)
    if row is None:
        raise ConsoleEditorError(
            "editor_target_unknown", "Target is absent from the canonical Dragon inventory"
        )
    native_key = "game_boy" if key in {"game_boy_pocket", "game_boy_light"} else key
    known_aliases = {
        "game_boy_advance_sp": "game_boy_advance",
        "game_boy_micro": "game_boy_advance",
        "super_game_boy": "game_boy",
        "super_game_boy_2": "game_boy",
    }
    native_key = known_aliases.get(native_key, native_key)
    native = dict(_NATIVE.get(native_key, {}))
    if key == "game_gear":
        native = {
            **_NATIVE["master_system"],
            "palette_format": "gg_bgr444",
            "scope": "GameGear Mode4 VDP and12bit CRAM",
        }
    maximum_width, maximum_height = min(row["max_width"], 2048), min(row["max_height"], 1536)
    limits = {
        "viewport_width": max(8, maximum_width),
        "viewport_height": max(8, maximum_height),
        "palette_colors": (
            256
            if native_key == "game_boy_advance"
            else native.get("palette_colors", min(256, row["max_colors"]))
        ),
        "palette_banks": native.get("palette_banks", 16),
        "tile_banks": native.get("tile_banks", 8),
        "tiles_per_bank": native.get("tiles_per_bank", 2048),
        "map_width": 256,
        "map_height": 256,
        "layers": 8,
        "entities": 256,
        "assets": 128,
        "audio_cues": 64,
        "project_json_bytes": MAX_PROJECT_BYTES,
    }
    payload = {
        "schema_version": "skeleton.console_editor_profile.v1",
        "target_id": key,
        "label": key.replace("_", " "),
        "family": row["family"],
        "generation": row["generation"],
        "cpu": row["cpu"],
        "graphics": row["graphics"],
        "sound": row["sound"],
        "input": row["input"],
        "sections": ["source", "tiles", "palettes", "maps", "scenes", "controllers", "audio", "config"],
        "entity_kinds": sorted(_KINDS),
        "collision_types": sorted(_COLLISIONS),
        "physical_display_colors": row["max_colors"],
        "config_ranges": {
            "gravity": [0, 4000],
            "speed": [1, 600],
            "jump_speed": [1, 1000],
            "attack_damage": [1, 100],
            "attack_range": [1, 256],
            "day_length_seconds": [1, 3600],
            "season_days": [1, 365],
            "crop_growth_days": [1, 90],
            "fishing_probability": [0, 1],
        },
        "config_choices": {"movement_mode": ["top_down", "platformer"], "tick_hz": [60]},
        "asset_codecs": {
            "tiles": native.get("codecs", [native.get("codec", "indexed_8bpp")]),
            "image": ["png", "rgba8888", "ps1_tim"],
            "audio": ["pcm_wav"],
            "data": ["raw"],
        },
        "controller_actions": list(_ACTIONS),
        "available_capabilities": {
            "editable_scene": True,
            "original_asset_authoring": True,
            "native_tile_codec": bool(native),
            "tim_codec": key == "ps1",
            "design_scene_simulation": True,
            "hardware_emulation": False,
            "source_generation": bool(row["supported_styles"]),
        },
        "toolchain_readiness": {
            "status": row["status"],
            "toolchain": row["toolchain"],
            "build_verified": False,
            "sdk_installed": None,
            "source_styles": list(row["supported_styles"]),
            "reason": "Actual compiler readiness/build receipts remain owned by the canonical fixed toolchain boundary",
        },
        "manifest_schema": PROJECT_SCHEMA,
        "document_path": PROJECT_PATH,
        "limits": limits,
        "native_constraints": native
        or {
            "scope": "Hardware-specific binary/memory constraints unavailable; portable authoring limits are not physical hardware facts",
            "vram_bytes": None,
            "rom_bank_bytes": None,
            "endianness": None,
        },
        "default_codec": native.get("codec", "indexed_8bpp"),
        "palette_format": native.get("palette_format", "rgba8888"),
        "target_metadata_digest": _digest(row),
    }
    return ConsoleEditorProfile(key, payload["label"], _json(payload).decode())


def console_editor_catalog() -> tuple[dict, ...]:
    return tuple(console_profile(row["id"]).as_dict() for row in _catalog())


def _unique(rows: object, maximum: int, label: str) -> list[dict]:
    if (
        not isinstance(rows, (tuple, list))
        or len(rows) > maximum
        or any(not isinstance(row, Mapping) for row in rows)
    ):
        raise ConsoleEditorError("editor_document_invalid", f"{label} must be a bounded record sequence")
    result, seen = [], set()
    for row in rows:
        key = _id(row.get("id"), label + " ID")
        if key in seen:
            raise ConsoleEditorError("editor_identity_conflict", f"{label} IDs must be unique")
        seen.add(key)
        result.append(dict(row))
    return result


def _config(value: object) -> dict:
    defaults = {
        "movement_mode": "top_down",
        "gravity": 400.0,
        "speed": 72.0,
        "jump_speed": 180.0,
        "attack_damage": 1,
        "attack_range": 18.0,
        "day_length_seconds": 60.0,
        "season_days": 7,
        "crop_growth_days": 2,
        "fishing_probability": 0.25,
        "background_color": "#182b20ff",
        "camera_follow": True,
        "end_on_goal": False,
        "tick_hz": 60,
    }
    if not isinstance(value, Mapping) or set(value) - set(defaults):
        raise ConsoleEditorError("editor_config_invalid", "Configuration contains unsupported controls")
    result = {**defaults, **value}
    if (
        result["movement_mode"] not in {"top_down", "platformer"}
        or type(result["camera_follow"]) is not bool
        or type(result["end_on_goal"]) is not bool
        or result["tick_hz"] != 60
        or type(result["tick_hz"]) is not int
    ):
        raise ConsoleEditorError(
            "editor_config_invalid", "Design simulation requires declared movement mode and fixed60Hz"
        )
    for key, low, high in (
        ("gravity", 0, 4000),
        ("speed", 1, 600),
        ("jump_speed", 1, 1000),
        ("attack_range", 1, 256),
        ("day_length_seconds", 1, 3600),
        ("fishing_probability", 0, 1),
    ):
        result[key] = _number(result[key], low, high, key)
    for key, low, high in (("attack_damage", 1, 100), ("season_days", 1, 365), ("crop_growth_days", 1, 90)):
        result[key] = _int(result[key], low, high, key)
    result["background_color"] = color_hex(result["background_color"])
    return result


def _properties(kind: str, value: object) -> dict:
    base = {"color": "#ffffffff"}
    extras = {
        "player": {"health": 5},
        "goal": {"points": 10},
        "pickup": {"value": 1, "item": "money"},
        "hazard": {"damage": 1},
        "platform": {"one_way": False},
        "crop": {"growth_days": None, "yield": 2, "planted": True, "requires_water": True},
        "npc": {"dialogue": "Hello, traveler.", "quest_type": "none", "required_count": 1, "reward": 5},
        "water": {"fishing_probability": None, "fish_value": 1},
        "enemy": {"health": 2, "damage": 1, "speed": 12.0, "patrol_range": 32.0},
        "portal": {"destination_x": 0.0, "destination_y": 0.0},
        "decoration": {},
    }
    allowed = {**base, **extras[kind]}
    if not isinstance(value, Mapping) or set(value) - set(allowed):
        raise ConsoleEditorError("editor_entity_property", "Entity properties do not match the declared kind")
    result = {**allowed, **value}
    result["color"] = color_hex(result["color"])
    for key in set(result) & {
        "health",
        "damage",
        "points",
        "value",
        "yield",
        "growth_days",
        "required_count",
        "reward",
        "fish_value",
    }:
        if key == "growth_days" and result[key] is None:
            continue
        result[key] = _int(result[key], 1, 1000 if key == "points" else 100, key)
    for key in set(result) & {"planted", "requires_water", "one_way"}:
        if type(result[key]) is not bool:
            raise ConsoleEditorError("editor_entity_property", "Entity property requires an exact boolean")
    for key in set(result) & {
        "speed",
        "patrol_range",
        "destination_x",
        "destination_y",
        "fishing_probability",
    }:
        if key == "fishing_probability" and result[key] is None:
            continue
        result[key] = _number(
            result[key], 0, 1 if key == "fishing_probability" else 2048 if key == "speed" else 65536, key
        )
    if "item" in result and result["item"] not in {"money", "health", "seed"}:
        raise ConsoleEditorError("editor_entity_property", "Pickup item is unknown")
    if "quest_type" in result and result["quest_type"] not in {
        "none",
        "deliver_crop",
        "catch_fish",
        "visit_goal",
    }:
        raise ConsoleEditorError("editor_entity_property", "NPC quest type is unknown")
    if "dialogue" in result and (not isinstance(result["dialogue"], str) or len(result["dialogue"]) > 512):
        raise ConsoleEditorError("editor_entity_property", "NPC dialogue exceeds bounded text")
    return result


def _document(value: Mapping) -> dict:
    expected = {
        "schema_version",
        "project_id",
        "title",
        "target_id",
        "profile_digest",
        "viewport",
        "tile_size",
        "palettes",
        "tilesets",
        "layers",
        "entities",
        "controls",
        "audio",
        "config",
        "assets",
    }
    if not isinstance(value, Mapping) or set(value) != expected or value["schema_version"] != PROJECT_SCHEMA:
        raise ConsoleEditorError("editor_document_invalid", "Editor project schema or fields differ")
    _json(value)
    result = json.loads(_json(value))
    profile = console_profile(result["target_id"]).as_dict()
    limits = profile["limits"]
    if result["target_id"] != profile["target_id"] or result["profile_digest"] != profile["profile_digest"]:
        raise ConsoleEditorError(
            "editor_profile_changed", "Project target profile identity differs from current canonical target"
        )
    _id(result["project_id"], "project ID")
    if (
        not isinstance(result["title"], str)
        or not 1 <= len(result["title"]) <= 120
        or any(ord(char) < 32 for char in result["title"])
    ):
        raise ConsoleEditorError("editor_title_invalid", "Title must be bounded printable text")
    if (
        not isinstance(result["viewport"], Mapping)
        or set(result["viewport"]) != {"width", "height"}
        or result["tile_size"] != 8
        or type(result["tile_size"]) is not int
    ):
        raise ConsoleEditorError(
            "editor_viewport_invalid", "Editor viewport requires integer dimensions and8pixeltiles"
        )
    _int(result["viewport"]["width"], 8, limits["viewport_width"], "viewport width")
    _int(result["viewport"]["height"], 8, limits["viewport_height"], "viewport height")
    palettes = _unique(result["palettes"], limits["palette_banks"], "palettes")
    if not palettes:
        raise ConsoleEditorError("editor_palette_invalid", "Project requires an authored palette")
    for row in palettes:
        if (
            set(row) != {"id", "colors"}
            or not isinstance(row["colors"], list)
            or not 1 <= len(row["colors"]) <= limits["palette_colors"]
        ):
            raise ConsoleEditorError("editor_palette_invalid", "Palette fields/color capacity differ")
        row["colors"] = [color_hex(color) for color in row["colors"]]
    native_colors = profile["native_constraints"].get("palette_colors", 256) * profile[
        "native_constraints"
    ].get("palette_banks", 16)
    if (
        profile["available_capabilities"]["native_tile_codec"]
        and sum(len(row["colors"]) for row in palettes) > native_colors
    ):
        raise ConsoleEditorError(
            "editor_palette_capacity", "Authored palettes exceed the declared native palette word budget"
        )
    palette_by = {row["id"]: row for row in palettes}
    tilesets = _unique(result["tilesets"], limits["tile_banks"] * 8, "tilesets")
    bank_slots = {}
    for row in tilesets:
        if set(row) != {"id", "codec", "palette_id", "tiles", "bank"} or row["palette_id"] not in palette_by:
            raise ConsoleEditorError(
                "editor_tileset_invalid", "Tileset requires exact fields and an existing palette"
            )
        bank = _int(row["bank"], 0, limits["tile_banks"] - 1, "tile bank")
        tile_codec_descriptor(row["codec"])
        supported = profile["native_constraints"].get("codecs", [profile["default_codec"]])
        if row["codec"] not in supported:
            raise ConsoleEditorError(
                "editor_codec_incompatible", "Tile codec is outside this target authoring profile"
            )
        encoded = encode_tiles(row["tiles"], row["codec"])
        if any(max(tile) >= len(palette_by[row["palette_id"]]["colors"]) for tile in row["tiles"]):
            raise ConsoleEditorError("editor_palette_reference", "Tile references an absent palette color")
        bank_slots[bank] = bank_slots.get(bank, 0) + len(row["tiles"])
        if bank_slots[bank] > limits["tiles_per_bank"] or len(encoded) > 131072:
            raise ConsoleEditorError(
                "editor_tile_bank_limit", "Tiles exceed the declared bank/index capacity"
            )
        row["tiles"] = [list(tile) for tile in row["tiles"]]
    if not tilesets:
        raise ConsoleEditorError("editor_tileset_invalid", "Project requires an authored tileset")
    tileset_by = {row["id"]: row for row in tilesets}
    layers = _unique(result["layers"], limits["layers"], "layers")
    if not layers:
        raise ConsoleEditorError("editor_layer_invalid", "Project requires at least one layer")
    for row in layers:
        if (
            set(row) != {"id", "width", "height", "cells", "visible", "offset", "z"}
            or type(row["visible"]) is not bool
        ):
            raise ConsoleEditorError("editor_layer_invalid", "Layer fields or visibility differ")
        width = _int(row["width"], 1, limits["map_width"], "map width")
        height = _int(row["height"], 1, limits["map_height"], "map height")
        if (
            not isinstance(row["cells"], list)
            or len(row["cells"]) != width * height
            or len(row["cells"]) > 65536
        ):
            raise ConsoleEditorError("editor_map_shape", "Tilemap cell count differs from dimensions")
        if not isinstance(row["offset"], list) or len(row["offset"]) != 2:
            raise ConsoleEditorError("editor_layer_offset", "Layer offset requires two finite coordinates")
        row["offset"] = [_number(value, -65536, 65536, "layer offset") for value in row["offset"]]
        _int(row["z"], -32, 32, "layer depth")
        for cell in row["cells"]:
            if (
                not isinstance(cell, Mapping)
                or set(cell) != {"tile", "tileset_id", "palette_id", "flip_x", "flip_y", "collision"}
                or type(cell["flip_x"]) is not bool
                or type(cell["flip_y"]) is not bool
                or cell["collision"] not in _COLLISIONS
            ):
                raise ConsoleEditorError("editor_map_cell", "Tile cell fields or collision differ")
            if cell["tileset_id"] not in tileset_by or cell["palette_id"] not in palette_by:
                raise ConsoleEditorError(
                    "editor_map_reference", "Tilemap references an absent tileset/palette"
                )
            _int(cell["tile"], 0, len(tileset_by[cell["tileset_id"]]["tiles"]) - 1, "tile index")
            tile = tileset_by[cell["tileset_id"]]["tiles"][cell["tile"]]
            if max(tile) >= len(palette_by[cell["palette_id"]]["colors"]):
                raise ConsoleEditorError(
                    "editor_map_reference", "Map palette cannot display the selected tile"
                )
    layer_by = {row["id"]: row for row in layers}
    assets = _unique(result["assets"], limits["assets"], "assets")
    decoded_asset_bytes = 0
    for row in assets:
        allowed = {"id", "kind", "codec", "data_base64", "metadata", "provenance"}
        if (
            set(row) != allowed
            or row["kind"] not in {"tiles", "image", "palette", "audio", "data"}
            or not isinstance(row["data_base64"], str)
            or len(row["data_base64"]) > 4 * ((MAX_FILE_BYTES + 2) // 3)
        ):
            raise ConsoleEditorError("editor_asset_invalid", "Asset record or byte capacity differs")
        try:
            data = base64.b64decode(row["data_base64"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ConsoleEditorError("editor_asset_invalid", "Asset encoding is invalid") from exc
        provenance = row["provenance"]
        if (
            not isinstance(provenance, Mapping)
            or set(provenance) != {"kind", "author_ref", "source_digest", "transformations"}
            or provenance["kind"] != "original_authoring"
        ):
            raise ConsoleEditorError(
                "editor_asset_provenance", "Original authored asset provenance is required"
            )
        receipt = asset_receipt(
            data,
            asset_id=row["id"],
            kind=row["kind"],
            codec=row["codec"],
            author_ref=provenance["author_ref"],
            source_digest=provenance["source_digest"],
            transformations=provenance["transformations"],
        )
        if not isinstance(row["metadata"], Mapping) or len(_json(row["metadata"], 16384)) > 16384:
            raise ConsoleEditorError("editor_asset_metadata", "Asset metadata exceeds capacity")
        if row["kind"] == "tiles":
            decode_tiles(data, row["codec"])
        elif row["codec"] == "ps1_tim":
            if row["kind"] != "image":
                raise ConsoleEditorError("editor_asset_codec", "TIM assets are images")
            image = decode_tim(data)
            metadata = row["metadata"]
            measured = {"width": image.width, "height": image.height, "bits_per_pixel": image.bits_per_pixel}
            if any(key in metadata and metadata[key] != value for key, value in measured.items()):
                raise ConsoleEditorError(
                    "editor_asset_shape", "TIM metadata differs from decoded source geometry"
                )
            row["metadata"] = {**metadata, **measured}
            decoded_asset_bytes += image.width * image.height * 4
        elif row["kind"] == "image" and row["codec"] == "png":
            width, height, rgba = decode_png(data)
            if any(
                key in row["metadata"] and row["metadata"][key] != value
                for key, value in (("width", width), ("height", height))
            ):
                raise ConsoleEditorError(
                    "editor_asset_shape", "PNG metadata differs from actual decoded geometry"
                )
            row["metadata"] = {
                **row["metadata"],
                "width": width,
                "height": height,
                "pixel_digest": hashlib.sha256(rgba).hexdigest(),
            }
            decoded_asset_bytes += len(rgba)
        elif row["kind"] == "audio" and row["codec"] == "pcm_wav":
            measured = decode_pcm_wav(data)
            measured.pop("pcm")
            if any(
                key in row["metadata"] and row["metadata"][key] != value for key, value in measured.items()
            ):
                raise ConsoleEditorError("editor_asset_shape", "PCM metadata differs from actual samples")
            row["metadata"] = {**row["metadata"], **measured}
        elif row["kind"] == "palette":
            decode_palette(data, row["codec"])
        elif row["kind"] == "image" and row["codec"] == "rgba8888":
            metadata = row["metadata"]
            width = _int(metadata.get("width"), 1, 1024, "image width")
            height = _int(metadata.get("height"), 1, 1024, "image height")
            if len(data) != width * height * 4:
                raise ConsoleEditorError("editor_asset_shape", "RGBA asset bytes differ from dimensions")
        elif row["kind"] != "data" or row["codec"] != "raw":
            raise ConsoleEditorError(
                "editor_asset_codec", "Unknown kind/codec pair is not executable image/audio evidence"
            )
        if row["kind"] == "image" and row["codec"] == "rgba8888":
            decoded_asset_bytes += len(data)
        if decoded_asset_bytes > 8 * 1024 * 1024:
            raise ConsoleEditorError("editor_asset_decoded_limit", "Decoded image aggregate exceeds8MiB")
        row["provenance"] = receipt["provenance"]
    asset_by = {row["id"]: row for row in assets}
    entities = _unique(result["entities"], limits["entities"], "entities")
    players = 0
    for row in entities:
        if (
            set(row) != {"id", "kind", "x", "y", "width", "height", "asset_id", "layer_id", "properties"}
            or row["kind"] not in _KINDS
            or row["layer_id"] not in layer_by
            or row["asset_id"] is not None
            and row["asset_id"] not in asset_by
        ):
            raise ConsoleEditorError("editor_entity_invalid", "Entity fields/kind/references differ")
        for key in ("x", "y"):
            row[key] = _number(row[key], 0, 65536, "entity position")
        for key in ("width", "height"):
            row[key] = _number(row[key], 1, 256, "entity size")
        row["properties"] = _properties(row["kind"], row["properties"])
        players += row["kind"] == "player"
    if players != 1:
        raise ConsoleEditorError("editor_player_count", "Design scene requires exactly one authored player")
    controls = result["controls"]
    if (
        not isinstance(controls, Mapping)
        or set(controls) != {"bindings"}
        or not isinstance(controls["bindings"], Mapping)
        or set(controls["bindings"]) - set(_ACTIONS)
    ):
        raise ConsoleEditorError(
            "editor_controls_invalid", "Control bindings must name actual design actions"
        )
    for key, binding in controls["bindings"].items():
        if (
            not isinstance(binding, str)
            or not 1 <= len(binding) <= 64
            or any(ord(char) < 32 for char in binding)
        ):
            raise ConsoleEditorError("editor_controls_invalid", "Control binding exceeds bounded text")
    audio = result["audio"]
    if not isinstance(audio, Mapping) or set(audio) != {"cues"}:
        raise ConsoleEditorError("editor_audio_invalid", "Audio requires a cue sequence")
    cues = _unique(audio["cues"], limits["audio_cues"], "audio cues")
    for cue in cues:
        cue.setdefault("asset_id", None)
        if cue["asset_id"] is not None and (
            cue["asset_id"] not in asset_by
            or asset_by[cue["asset_id"]]["kind"] != "audio"
            or asset_by[cue["asset_id"]]["codec"] != "pcm_wav"
        ):
            raise ConsoleEditorError(
                "editor_audio_asset", "Audio cue must reference actual measuredPCM asset"
            )
        if (
            set(cue)
            != {"id", "event", "waveform", "frequency", "duration", "gain", "attack", "release", "asset_id"}
            or cue["event"]
            not in {"pickup", "attack", "damage", "goal", "water", "plant", "harvest", "fish", "quest"}
            or cue["waveform"] not in {"sine", "square", "triangle", "noise"}
        ):
            raise ConsoleEditorError("editor_audio_invalid", "Audio cue shape/event/waveform differs")
        for key, low, high in (
            ("frequency", 20, 12000),
            ("duration", 0.005, 2),
            ("gain", 0, 1),
            ("attack", 0, 2),
            ("release", 0, 2),
        ):
            cue[key] = _number(cue[key], low, high, "audio " + key)
        if cue["attack"] + cue["release"] > cue["duration"]:
            raise ConsoleEditorError("editor_audio_envelope", "Attack/release exceed actual cue duration")
    result.update(
        palettes=palettes,
        tilesets=tilesets,
        layers=layers,
        entities=entities,
        assets=assets,
        audio={"cues": cues},
        config=_config(result["config"]),
    )
    _json(result)
    return result


@dataclass(frozen=True, slots=True)
class ConsoleValidationReport:
    valid: bool
    target_id: str
    profile_digest: str
    document_digest: str
    errors: tuple[dict, ...] = ()
    warnings: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {
            "valid": self.valid,
            "target_id": self.target_id,
            "profile_digest": self.profile_digest,
            "document_digest": self.document_digest,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "hardware_compatibility_verified": False,
        }


class ConsoleProject:
    def __init__(self, document: Mapping, files: Mapping[str, str] | None = None):
        normalized = _document(document)
        self._document_json = _json(normalized).decode()
        self._files = MappingProxyType(_files(files or {}))
        try:
            self._scene_graph = ConsoleSceneGraph(
                (
                    _load(self._files[GRAPH_PATH])
                    if GRAPH_PATH in self._files
                    else empty_scene_graph(normalized["project_id"])
                ),
                normalized,
            )
        except SceneGraphError as exc:
            raise ConsoleEditorError(exc.code, str(exc), exc.status_code) from exc

    @classmethod
    def from_files(cls, files: Mapping[str, str], *, target_id: str | None = None) -> ConsoleProject:
        files = _files(files)
        if PROJECT_PATH not in files:
            raise ConsoleEditorError(
                "editor_document_missing", "Project has no canonical console editor document"
            )
        document = _load(files[PROJECT_PATH])
        project = cls(document, files)
        if target_id is not None and _target_id(target_id) != project.target_id:
            raise ConsoleEditorError("editor_target_conflict", "Requested console and editor document differ")
        return project

    @property
    def scene_graph(self) -> ConsoleSceneGraph:
        return self._scene_graph

    @property
    def target_id(self) -> str:
        return self.as_dict()["target_id"]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self._document_json.encode()).hexdigest()

    @property
    def manifest_digest(self) -> str:
        return file_manifest_digest(self.export_files())

    def as_dict(self) -> dict:
        return json.loads(self._document_json)

    def export_files(self) -> dict[str, str]:
        return _files({**self._files, PROJECT_PATH: self._document_json + "\n"})

    def validate(self) -> ConsoleValidationReport:
        document = _document(self.as_dict())
        profile = console_profile(self.target_id).as_dict()
        warnings = []
        if not profile["available_capabilities"]["native_tile_codec"]:
            warnings.append(
                {
                    "code": "portable_authoring_profile",
                    "message": "Hardware binary/memory constraints unavailable; scene remains a design simulation",
                }
            )
        maximum = profile["native_constraints"].get("hardware_sprites")
        if maximum is not None and len(document["entities"]) > maximum:
            warnings.append(
                {
                    "code": "hardware_sprite_count",
                    "message": "Scene entities exceed simultaneous hardware sprite count; source port requires culling/multiplexing",
                }
            )
        for layer in document["layers"]:
            native = profile["native_constraints"]
            if native.get("map_width") and (
                layer["width"] > native["map_width"] or layer["height"] > native["map_height"]
            ):
                warnings.append(
                    {
                        "code": "native_map_requires_chunking",
                        "layer_id": layer["id"],
                        "message": "Design map exceeds a native map plane and needs source-level chunk/scroll integration",
                    }
                )
        return ConsoleValidationReport(
            True, self.target_id, profile["profile_digest"], self.digest, (), tuple(warnings)
        )

    @property
    def source_manifest_digest(self) -> str:
        raw = self._files.get("game/editor/source_manifest.json")
        if raw is None:
            return self.manifest_digest
        metadata = _load(raw, 1024)
        if (
            set(metadata) != {"schema_version", "manifest_digest"}
            or metadata["schema_version"] != "skeleton.console_editor_source_identity.v1"
            or not isinstance(metadata["manifest_digest"], str)
            or not _SHA.fullmatch(metadata["manifest_digest"])
        ):
            raise ConsoleEditorError(
                "editor_source_identity", "Compact execution source manifest identity differs"
            )
        return metadata["manifest_digest"]

    def build_handoff(self) -> dict:
        profile = console_profile(self.target_id).as_dict()
        assets, asset_projection = _native_projection(self.as_dict(), profile)
        try:
            materialized_sources = self.native_source_files()
            materialization_error = None
        except (ConsoleEditorError, ConsoleAssetError) as exc:
            materialized_sources = {}
            materialization_error = {"code": exc.code, "message": str(exc)}
        binding_status = _native_binding_status(self)
        return {
            "schema_version": "skeleton.console_editor_build_handoff.v1",
            "target_id": self.target_id,
            "document_digest": self.digest,
            "manifest_digest": self.manifest_digest,
            "profile_digest": profile["profile_digest"],
            "source_files": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "bytes": len(text.encode()),
                }
                for name, text in sorted(self.export_files().items())
                if PurePosixPath(name).suffix.lower() in {".c", ".cpp", ".cc", ".s", ".asm", ".h", ".hpp"}
            ],
            "native_asset_projection": asset_projection,
            "source_materialization_error": materialization_error,
            "materialized_source_files": [
                {
                    "path": name,
                    "bytes": len(text.encode()),
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                }
                for name, text in sorted(materialized_sources.items())
            ],
            "native_assets": [
                {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                for name, data in sorted(assets.items())
            ],
            "toolchain_readiness": profile["toolchain_readiness"],
            "source_integration_required": binding_status["source_integration_required"],
            "native_binding": binding_status,
            "native_execution_verified": False,
            "validation": self.validate().as_dict(),
        }

    def native_asset_files(self) -> dict[str, bytes]:
        assets, _ = _native_projection(self.as_dict(), console_profile(self.target_id).as_dict())
        return assets

    def native_starter_source_files(self) -> dict[str, str]:
        return native_starter_source_files(self)

    def native_source_files(self) -> dict[str, str]:
        return native_source_files(self)


def create_console_project(
    target_id: str, *, project_id: str, title: str, seed: int = 1, files: Mapping[str, str] | None = None
) -> ConsoleProject:
    profile = console_profile(target_id).as_dict()
    _int(seed, 0, 2**63 - 1, "authoring seed")
    width, height = min(profile["limits"]["viewport_width"], 320), min(
        profile["limits"]["viewport_height"], 224
    )
    shades = (
        ["#ffffffff", "#aaaaaaff", "#555555ff", "#000000ff"]
        if profile["palette_format"] == "dmg_gray"
        else ["#1c3428ff", "#4c8c44ff", "#cce47cff", "#f8fcf4ff"]
    )
    colors = shades[: profile["limits"]["palette_colors"]]
    tiles = [
        [0] * 64,
        [1 if (x + y + seed) % 4 else 0 for y in range(8) for x in range(8)],
        [2 if x in (0, 7) or y in (0, 7) else 1 for y in range(8) for x in range(8)],
        [3 if x == y or x == 7 - y else 0 for y in range(8) for x in range(8)],
    ]
    tiles = [[value % len(colors) for value in tile] for tile in tiles]
    map_width, map_height = max(8, width // 8), max(8, height // 8)

    def cell(x, y):
        border = x in (0, map_width - 1) or y in (0, map_height - 1)
        return {
            "tile": 2 if border else 1,
            "tileset_id": "terrain",
            "palette_id": "main",
            "flip_x": False,
            "flip_y": False,
            "collision": "solid" if border else "none",
        }

    def entity(identity, kind, x, y, color):
        return {
            "id": identity,
            "kind": kind,
            "x": x,
            "y": y,
            "width": 8,
            "height": 8,
            "asset_id": None,
            "layer_id": "ground",
            "properties": {"color": color},
        }

    entities = [
        entity("player", "player", 16, 16, "#fff078ff"),
        entity("goal", "goal", max(24, width - 24), max(24, height - 24), "#78f0c0ff"),
        entity("plot", "crop", 40, 32, "#88d060ff"),
        entity("pond", "water", 56, 32, "#3878c8ff"),
        entity("neighbor", "npc", 32, 48, "#f09080ff"),
    ]
    document = {
        "schema_version": PROJECT_SCHEMA,
        "project_id": project_id,
        "title": title,
        "target_id": profile["target_id"],
        "profile_digest": profile["profile_digest"],
        "viewport": {"width": width, "height": height},
        "tile_size": 8,
        "palettes": [{"id": "main", "colors": colors}],
        "tilesets": [
            {
                "id": "terrain",
                "codec": profile["default_codec"],
                "palette_id": "main",
                "tiles": tiles,
                "bank": 0,
            }
        ],
        "layers": [
            {
                "id": "ground",
                "width": map_width,
                "height": map_height,
                "cells": [cell(x, y) for y in range(map_height) for x in range(map_width)],
                "visible": True,
                "offset": [0, 0],
                "z": 0,
            }
        ],
        "entities": entities,
        "controls": {
            "bindings": {
                "left": "ArrowLeft",
                "right": "ArrowRight",
                "up": "ArrowUp",
                "down": "ArrowDown",
                "interact": "KeyE",
                "water": "KeyW",
                "plant": "KeyP",
                "fish": "KeyF",
                "attack": "Space",
                "jump": "KeyZ",
            }
        },
        "audio": {
            "cues": [
                {
                    "id": "pickup",
                    "event": "pickup",
                    "waveform": "sine",
                    "frequency": 880,
                    "duration": 0.08,
                    "gain": 0.15,
                    "attack": 0.005,
                    "release": 0.03,
                }
            ]
        },
        "config": _config({}),
        "assets": [],
    }
    return ConsoleProject(document, files)


@dataclass(frozen=True, slots=True)
class ConsoleEditResult:
    files: Mapping[str, str]
    manifest_digest: str
    project: ConsoleProject
    changes: tuple[dict, ...]
    validation: ConsoleValidationReport

    def as_dict(self) -> dict:
        return {
            "files": dict(self.files),
            "manifest_digest": self.manifest_digest,
            "document": self.project.as_dict(),
            "scene_graph": self.project.scene_graph.as_dict(),
            "changes": list(self.changes),
            "validation": self.validation.as_dict(),
        }


def apply_console_edits(
    files: Mapping[str, str],
    *,
    target_id: str,
    edits: Sequence[Mapping],
    expected_manifest_digest: str,
    project_id: str | None = None,
) -> ConsoleEditResult:
    source_files = _files(files)
    if (
        not isinstance(expected_manifest_digest, str)
        or not _SHA.fullmatch(expected_manifest_digest)
        or file_manifest_digest(source_files) != expected_manifest_digest
    ):
        raise ConsoleEditorError(
            "editor_manifest_conflict", "Exact project file manifest changed before edit admission", 409
        )
    project = ConsoleProject.from_files(source_files, target_id=target_id)
    document = project.as_dict()
    graph = project.scene_graph.as_dict()
    if project_id is not None and document["project_id"] != project_id:
        raise ConsoleEditorError(
            "editor_identity_conflict", "Project ID differs from the committed editor document", 409
        )
    if not isinstance(edits, (tuple, list)) or not 1 <= len(edits) <= 256:
        raise ConsoleEditorError("editor_edit_limit", "A bounded nonempty typed edit sequence is required")
    changes, identities = [], {}
    for edit in edits:
        if not isinstance(edit, Mapping):
            raise ConsoleEditorError("editor_edit_invalid", "Editor patch must be a typed object")
        _json(edit, MAX_PROJECT_BYTES)
        op = edit.get("op")
        edit = dict(edit)
        identity = edit.pop("edit_id", None)
        if identity is not None:
            _id(identity, "edit ID")
            digest = _digest(edit)
            if identity in identities:
                if identities[identity] != digest:
                    raise ConsoleEditorError(
                        "editor_edit_conflict", "An edit ID was reused for another request", 409
                    )
                continue
            identities[identity] = digest

        def find(kind, key):
            row = next((row for row in document[kind] if row["id"] == key), None)
            if row is None:
                raise ConsoleEditorError("editor_reference_missing", "Typed edit refers to an absent record")
            return row

        if op == "set_scene_graph":
            if set(edit) != {"op", "graph"} or not isinstance(edit["graph"], Mapping):
                raise ConsoleEditorError("editor_edit_invalid", "Scene graph edit fields differ")
            graph = json.loads(_json(edit["graph"], 512 * 1024))
            source_files[GRAPH_PATH] = _json(graph).decode() + "\n"
        elif op in {"upsert_graph_node", "upsert_animation", "upsert_rule", "upsert_variable"}:
            key, group = {
                "upsert_graph_node": ("node", "nodes"),
                "upsert_animation": ("animation", "animations"),
                "upsert_rule": ("rule", "rules"),
                "upsert_variable": ("variable", "variables"),
            }[op]
            if set(edit) != {"op", key} or not isinstance(edit[key], Mapping):
                raise ConsoleEditorError("editor_edit_invalid", "Graph record edit fields differ")
            row = json.loads(_json(edit[key]))
            _id(row.get("id"))
            graph[group] = [item for item in graph[group] if item["id"] != row["id"]] + [row]
            source_files[GRAPH_PATH] = _json(graph).decode() + "\n"
        elif op in {"remove_graph_node", "remove_animation", "remove_rule", "remove_variable"}:
            if set(edit) != {"op", "id"}:
                raise ConsoleEditorError("editor_edit_invalid", "Graph removal fields differ")
            group = {
                "remove_graph_node": "nodes",
                "remove_animation": "animations",
                "remove_rule": "rules",
                "remove_variable": "variables",
            }[op]
            if not any(row["id"] == edit["id"] for row in graph[group]):
                raise ConsoleEditorError(
                    "editor_reference_missing", "Graph removal refers to an absent record"
                )
            graph[group] = [row for row in graph[group] if row["id"] != edit["id"]]
            source_files[GRAPH_PATH] = _json(graph).decode() + "\n"
        elif op in {"set_tile", "paint_tile"}:
            row = find("tilesets", edit.get("tileset_id"))
            index = _int(edit.get("tile_index"), 0, len(row["tiles"]) - 1, "tile index")
            if op == "set_tile":
                if set(edit) != {"op", "tileset_id", "tile_index", "pixels"}:
                    raise ConsoleEditorError("editor_edit_invalid", "Tile edit fields differ")
                row["tiles"][index] = list(edit["pixels"])
            else:
                if set(edit) != {"op", "tileset_id", "tile_index", "x", "y", "color"}:
                    raise ConsoleEditorError("editor_edit_invalid", "Tile brush fields differ")
                x, y = _int(edit["x"], 0, 7, "pixel x"), _int(edit["y"], 0, 7, "pixel y")
                row["tiles"][index][y * 8 + x] = edit["color"]
        elif op == "set_palette":
            if set(edit) != {"op", "palette_id", "colors"}:
                raise ConsoleEditorError("editor_edit_invalid", "Palette edit fields differ")
            find("palettes", edit["palette_id"])["colors"] = edit["colors"]
        elif op in {"set_map_cell", "fill_map"}:
            row = find("layers", edit.get("layer_id"))
            x, y = _int(edit.get("x"), 0, row["width"] - 1, "map x"), _int(
                edit.get("y"), 0, row["height"] - 1, "map y"
            )
            width, height = (
                (1, 1)
                if op == "set_map_cell"
                else (
                    _int(edit.get("width"), 1, row["width"] - x, "fill width"),
                    _int(edit.get("height"), 1, row["height"] - y, "fill height"),
                )
            )
            fields = {"op", "layer_id", "x", "y", "cell"} | (
                {"width", "height"} if op == "fill_map" else set()
            )
            if set(edit) != fields:
                raise ConsoleEditorError("editor_edit_invalid", "Map brush fields differ")
            for dy in range(height):
                for dx in range(width):
                    row["cells"][(y + dy) * row["width"] + x + dx] = json.loads(_json(edit["cell"]))
        elif op in {"upsert_palette", "upsert_tileset"}:
            key = "palette" if op == "upsert_palette" else "tileset"
            group = "palettes" if key == "palette" else "tilesets"
            if set(edit) != {"op", key} or not isinstance(edit[key], Mapping):
                raise ConsoleEditorError("editor_edit_invalid", "Asset bank edit fields differ")
            row = dict(edit[key])
            _id(row.get("id"))
            document[group] = [existing for existing in document[group] if existing["id"] != row["id"]] + [
                row
            ]
        elif op == "transform_tile":
            if set(edit) != {"op", "tileset_id", "tile_index", "flip_x", "flip_y", "quarter_turns"}:
                raise ConsoleEditorError("editor_edit_invalid", "Tile transform fields differ")
            row = find("tilesets", edit["tileset_id"])
            index = _int(edit["tile_index"], 0, len(row["tiles"]) - 1, "tile index")
            palette = find("palettes", row["palette_id"])["colors"]
            image = IndexedImage(8, 8, bytes(row["tiles"][index]), tuple(palette)).transform(
                flip_x=edit["flip_x"], flip_y=edit["flip_y"], quarter_turns=edit["quarter_turns"]
            )
            row["tiles"][index] = list(image.pixels)
        elif op in {"upsert_layer", "upsert_entity"}:
            key = "layer" if op == "upsert_layer" else "entity"
            group = "layers" if key == "layer" else "entities"
            if set(edit) != {"op", key} or not isinstance(edit[key], Mapping):
                raise ConsoleEditorError("editor_edit_invalid", "Scene record edit fields differ")
            row = dict(edit[key])
            _id(row.get("id"))
            document[group] = [existing for existing in document[group] if existing["id"] != row["id"]] + [
                row
            ]
        elif op in {"remove_layer", "remove_entity", "delete_asset", "remove_palette", "remove_tileset"}:
            if set(edit) != {"op", "id"}:
                raise ConsoleEditorError("editor_edit_invalid", "Record removal fields differ")
            group = {
                "remove_layer": "layers",
                "remove_entity": "entities",
                "delete_asset": "assets",
                "remove_palette": "palettes",
                "remove_tileset": "tilesets",
            }[op]
            find(group, edit["id"])
            document[group] = [row for row in document[group] if row["id"] != edit["id"]]
        elif op in {"set_controls", "set_audio", "set_config"}:
            key = op.removeprefix("set_")
            if set(edit) != {"op", key}:
                raise ConsoleEditorError("editor_edit_invalid", "Project setting edit fields differ")
            document[key] = edit[key]
        elif op == "put_asset":
            if set(edit) != {"op", "asset"} or not isinstance(edit["asset"], Mapping):
                raise ConsoleEditorError("editor_edit_invalid", "Asset edit fields differ")
            row = dict(edit["asset"])
            _id(row.get("id"))
            document["assets"] = [
                existing for existing in document["assets"] if existing["id"] != row["id"]
            ] + [row]
        elif op == "transform_asset":
            if set(edit) != {"op", "id", "flip_x", "flip_y", "quarter_turns"}:
                raise ConsoleEditorError("editor_edit_invalid", "Asset transform fields differ")
            row = find("assets", edit["id"])
            if row["kind"] == "tiles":
                tiles = decode_tiles(base64.b64decode(row["data_base64"], validate=True), row["codec"])
                bits = tile_codec_descriptor(row["codec"])["bits_per_pixel"]
                palette = tuple((index, index, index, 255) for index in range(1 << bits))
                transformed = [
                    IndexedImage(8, 8, bytes(tile), palette)
                    .transform(
                        flip_x=edit["flip_x"], flip_y=edit["flip_y"], quarter_turns=edit["quarter_turns"]
                    )
                    .pixels
                    for tile in tiles
                ]
                data = encode_tiles(transformed, row["codec"])
                row["data_base64"] = base64.b64encode(data).decode()
                row["provenance"]["transformations"] = [*row["provenance"]["transformations"], _digest(edit)]
                changes.append({"op": op, "edit_id": identity, "request_digest": _digest(edit)})
                continue
            if row["codec"] in {"png", "rgba8888"}:
                data = base64.b64decode(row["data_base64"], validate=True)
                if row["codec"] == "png":
                    width, height, pixels = decode_png(data)
                else:
                    width, height, pixels = row["metadata"]["width"], row["metadata"]["height"], data
                width, height, pixels = transform_rgba(
                    pixels,
                    width,
                    height,
                    flip_x=edit["flip_x"],
                    flip_y=edit["flip_y"],
                    quarter_turns=edit["quarter_turns"],
                )
                data = png_rgba(pixels, width, height) if row["codec"] == "png" else pixels
                row["data_base64"] = base64.b64encode(data).decode()
                row["metadata"] = {"width": width, "height": height}
                row["provenance"]["transformations"] = [*row["provenance"]["transformations"], _digest(edit)]
                changes.append({"op": op, "edit_id": identity, "request_digest": _digest(edit)})
                continue
            if row["codec"] != "ps1_tim":
                raise ConsoleEditorError(
                    "editor_transform_unsupported",
                    "Typed pixel transforms currently require indexed TIM assets",
                )
            image = decode_tim(base64.b64decode(row["data_base64"], validate=True))
            transformed = transform_tim(
                image, flip_x=edit["flip_x"], flip_y=edit["flip_y"], quarter_turns=edit["quarter_turns"]
            )
            data = encode_tim(transformed)
            row["data_base64"] = base64.b64encode(data).decode()
            row["metadata"] = {
                "width": transformed.width,
                "height": transformed.height,
                "bits_per_pixel": transformed.bits_per_pixel,
            }
            row["provenance"]["transformations"] = [*row["provenance"]["transformations"], _digest(edit)]
        elif op == "image_to_tiles":
            if set(edit) != {"op", "asset_id", "tileset_id", "palette_id", "bank"}:
                raise ConsoleEditorError("editor_edit_invalid", "Native image conversion fields differ")
            asset = find("assets", edit["asset_id"])
            palette = find("palettes", edit["palette_id"])
            data = base64.b64decode(asset["data_base64"], validate=True)
            if asset["codec"] == "png":
                width, height, pixels = decode_png(data)
            elif asset["codec"] == "rgba8888":
                width, height, pixels = asset["metadata"]["width"], asset["metadata"]["height"], data
            elif asset["codec"] == "ps1_tim":
                image = decode_tim(data)
                width, height, pixels = image.width, image.height, image.rgba_bytes()
            else:
                raise ConsoleEditorError(
                    "editor_image_conversion", "Conversion requires measured original image data"
                )
            profile = console_profile(document["target_id"]).as_dict()
            tiles, receipt = image_to_tiles(
                pixels, width, height, palette["colors"], profile["default_codec"]
            )
            row = {
                "id": _id(edit["tileset_id"]),
                "codec": profile["default_codec"],
                "palette_id": palette["id"],
                "tiles": [list(tile) for tile in tiles],
                "bank": edit["bank"],
            }
            document["tilesets"] = [
                existing for existing in document["tilesets"] if existing["id"] != row["id"]
            ] + [row]
            asset["metadata"]["native_quantization"] = receipt
        elif op == "bind_native_starter":
            if set(edit) != {"op"}:
                raise ConsoleEditorError("editor_edit_invalid", "Native starter binding fields differ")
            candidate = ConsoleProject(document, source_files)
            generated = candidate.native_starter_source_files()
            prefix = f"game/generated/native/{candidate.target_id}/"
            source_files = {name: text for name, text in source_files.items() if not name.startswith(prefix)}
            source_files.update(generated)
        elif op == "unbind_native_starter":
            if set(edit) != {"op"}:
                raise ConsoleEditorError("editor_edit_invalid", "Native starter unbinding fields differ")
            source_files.pop("game/editor/native_binding.json", None)
        elif op == "materialize_assets":
            if set(edit) != {"op"}:
                raise ConsoleEditorError("editor_edit_invalid", "Native asset materialization fields differ")
            candidate = ConsoleProject(document, source_files)
            generated = candidate.native_source_files()
            source_files.update(generated)
        elif op == "replace_source":
            if set(edit) != {"op", "path", "content"} or edit["path"] in {PROJECT_PATH, GRAPH_PATH}:
                raise ConsoleEditorError(
                    "editor_edit_invalid", "Source edit must preserve typed editor document authority"
                )
            path = _path(edit["path"])
            if not isinstance(edit["content"], str):
                raise ConsoleEditorError("editor_edit_invalid", "Source edit content requires text")
            source_files[path] = edit["content"]
        else:
            raise ConsoleEditorError("editor_edit_unknown", "Typed editor operation is unknown")
        changes.append({"op": op, "edit_id": identity, "request_digest": _digest(edit)})
    updated = ConsoleProject(document, source_files)
    if "game/editor/native_binding.json" in source_files:
        generated = updated.native_starter_source_files()
        # Preserve explicitly edited executable source. Onlygenerateddata and
        # its exact source-binding descriptor are refreshed automatically.
        for name, text in generated.items():
            if name.endswith("assets.inc") or name == "game/editor/native_binding.json":
                source_files[name] = text
        updated = ConsoleProject(document, source_files)
    exported = updated.export_files()
    return ConsoleEditResult(
        MappingProxyType(exported),
        file_manifest_digest(exported),
        updated,
        tuple(changes),
        updated.validate(),
    )


def import_original_asset(
    data: bytes, *, asset_id: str, kind: str, codec: str, author_ref: str, metadata: Mapping | None = None
) -> dict:
    """Prepare original-authored data; current owner/rights remain backend gates."""
    metadata = json.loads(_json(metadata or {}, 16384))
    receipt = asset_receipt(data, asset_id=asset_id, kind=kind, codec=codec, author_ref=author_ref)
    if kind == "image" and codec == "png":
        width, height, rgba = decode_png(data)
        metadata.update(width=width, height=height, pixel_digest=hashlib.sha256(rgba).hexdigest())
    elif kind == "image" and codec == "ps1_tim":
        image = decode_tim(data)
        metadata.update(width=image.width, height=image.height, bits_per_pixel=image.bits_per_pixel)
    elif kind == "audio" and codec == "pcm_wav":
        measured = decode_pcm_wav(data)
        measured.pop("pcm")
        metadata.update(measured)
    elif kind == "tiles":
        tiles = decode_tiles(data, codec)
        metadata.update(tile_count=len(tiles), width=8, height=8)
    elif kind == "palette":
        colors = decode_palette(data, codec)
        metadata.update(colors=len(colors))
    elif kind != "data" or codec != "raw":
        if kind != "image" or codec != "rgba8888":
            raise ConsoleEditorError("editor_asset_codec", "Unknown original asset kind/codec")
    return {
        "id": asset_id,
        "kind": kind,
        "codec": codec,
        "data_base64": receipt["data_base64"],
        "metadata": metadata,
        "provenance": receipt["provenance"],
    }


def _native_projection(document: dict, profile: dict) -> tuple[dict[str, bytes], dict]:
    """Produce actual map/pattern/palette bytes and exact source placement hints."""
    target = profile["target_id"]
    target_alias = {
        "game_boy_pocket": "game_boy",
        "game_boy_light": "game_boy",
        "super_game_boy": "game_boy",
        "super_game_boy_2": "game_boy",
        "game_boy_advance_sp": "game_boy_advance",
        "game_boy_micro": "game_boy_advance",
        "game_gear": "master_system",
    }
    encoding_target = target_alias.get(target, target)
    native = profile["native_constraints"]
    result, placements = {}, []
    palettes = {row["id"]: row for row in document["palettes"]}
    palette_slots = {row["id"]: index for index, row in enumerate(document["palettes"])}
    banks = {}
    indices = {}
    tileset_by = {row["id"]: row for row in document["tilesets"]}
    bank_codecs = {}
    for row in document["tilesets"]:
        bank = row["bank"]
        if bank in bank_codecs and bank_codecs[bank] != row["codec"]:
            raise ConsoleEditorError(
                "editor_native_mixed_bank", "A native pattern bank cannot mix4/8bit tile layouts"
            )
        bank_codecs[bank] = row["codec"]
        patterns = banks.setdefault(bank, [])
        for index, tile in enumerate(row["tiles"]):
            indices[(row["id"], index)] = len(patterns)
            patterns.append(tuple(tile))
        result[f"game/editor/compiled/{row['id']}.tiles.bin"] = encode_tiles(row["tiles"], row["codec"])
    # PPU/DMG map entries cannot flip pixels. Bake exact mirrored originaltiles
    # into unused native pattern slots instead of claiming nonexistent flags.
    baked = {}
    for layer in document["layers"]:
        for cell in layer["cells"]:
            row = tileset_by[cell["tileset_id"]]
            bank = row["bank"]
            if encoding_target in {"nes", "game_boy"} and (cell["flip_x"] or cell["flip_y"]):
                key = (bank, cell["tileset_id"], cell["tile"], cell["flip_x"], cell["flip_y"])
                if key not in baked:
                    image = IndexedImage(
                        8, 8, bytes(row["tiles"][cell["tile"]]), tuple(palettes[cell["palette_id"]]["colors"])
                    )
                    tile = image.transform(flip_x=cell["flip_x"], flip_y=cell["flip_y"]).pixels
                    baked[key] = len(banks[bank])
                    banks[bank].append(tuple(tile))
    for bank, tiles in banks.items():
        if len(tiles) > profile["limits"]["tiles_per_bank"]:
            raise ConsoleEditorError(
                "editor_native_pattern_capacity",
                "Mirrored/merged tiles exceed actual native pattern index capacity",
            )
        data = encode_tiles(tiles, bank_codecs[bank])
        name = f"game/editor/compiled/bank_{bank}.patterns.bin"
        result[name] = data
        placements.append(
            {
                "path": name,
                "kind": "pattern_bank",
                "bank": bank,
                "tile_count": len(tiles),
                "codec": bank_codecs[bank],
                "bytes": len(data),
            }
        )
    palette_data = bytearray()
    pal_native = {}
    for row in document["palettes"]:
        data = encode_palette(row["colors"], profile["palette_format"])
        result[f"game/editor/compiled/{row['id']}.palette.bin"] = data
        slot = native.get("palette_colors", len(row["colors"]))
        if encoding_target == "game_boy_advance" and len(row["colors"]) > 16:
            if len(document["palettes"]) != 1:
                raise ConsoleEditorError(
                    "editor_native_gba_palette", "GBA8bpp requires one shared256color palette plane"
                )
            slot = 256
        if len(row["colors"]) > slot:
            raise ConsoleEditorError(
                "editor_native_palette_capacity", "Native palette row exceeds its hardware slot"
            )
        stride = (
            1
            if profile["palette_format"] in {"nes_palette_indices", "sms_rgb222", "dmg_gray"}
            else 4 if profile["palette_format"] == "rgba8888" else 2
        )
        padded = data + bytes((slot - len(row["colors"])) * stride)
        palette_data.extend(padded)
        pal_native[row["id"]] = data
        if encoding_target == "game_boy":
            register = sum(value << (2 * index) for index, value in enumerate(data))
            result[f"game/editor/compiled/{row['id']}.bgp.bin"] = bytes([register])
            placements.append(
                {
                    "path": f"game/editor/compiled/{row['id']}.bgp.bin",
                    "kind": "DMG_BGP_register",
                    "register_address": 0xFF47,
                    "value": register,
                }
            )
    if encoding_target == "nes" and len({data[0] for data in pal_native.values()}) > 1:
        raise ConsoleEditorError(
            "editor_native_nes_universal_color", "NES background palette entry0 is a shared universal color"
        )
    result["game/editor/compiled/palettes.bin"] = bytes(palette_data)
    native_maps = encoding_target in {
        "nes",
        "game_boy",
        "game_boy_color",
        "snes",
        "genesis",
        "game_boy_advance",
        "master_system",
    }
    if native_maps:
        chunk_width = 64 if encoding_target == "genesis" else 32
        chunk_height = 30 if encoding_target == "nes" else 28 if encoding_target == "master_system" else 32
        for layer in document["layers"]:
            for cy in range(0, layer["height"], chunk_height):
                for cx in range(0, layer["width"], chunk_width):
                    raw, attributes, palette_plane = bytearray(), bytearray(), []
                    for y in range(chunk_height):
                        for x in range(chunk_width):
                            if cx + x < layer["width"] and cy + y < layer["height"]:
                                cell = layer["cells"][(cy + y) * layer["width"] + cx + x]
                            else:
                                row = document["tilesets"][0]
                                cell = {
                                    "tile": 0,
                                    "tileset_id": row["id"],
                                    "palette_id": row["palette_id"],
                                    "flip_x": False,
                                    "flip_y": False,
                                    "collision": "none",
                                }
                            row = tileset_by[cell["tileset_id"]]
                            bank = row["bank"]
                            index = indices[(row["id"], cell["tile"])]
                            flip_x, flip_y = cell["flip_x"], cell["flip_y"]
                            if encoding_target in {"nes", "game_boy"}:
                                index = baked.get((bank, row["id"], cell["tile"], flip_x, flip_y), index)
                                flip_x = flip_y = False
                            palette = palette_slots[cell["palette_id"]]
                            if row["codec"] == "gba_8bpp":
                                palette = 0
                            if encoding_target == "nes":
                                if bank != 0:
                                    raise ConsoleEditorError(
                                        "editor_native_nes_bank",
                                        "BG map uses one selected256tile pattern table; bank1 is separately authored sprite data",
                                    )
                                raw.extend(tilemap_entry(target="nes", tile=index))
                                palette_plane.append(palette)
                            elif encoding_target == "game_boy_color":
                                entry = tilemap_entry(
                                    target=encoding_target,
                                    tile=index,
                                    palette=palette,
                                    bank=bank,
                                    flip_x=flip_x,
                                    flip_y=flip_y,
                                )
                                raw.append(entry[0])
                                attributes.append(entry[1])
                            else:
                                raw.extend(
                                    tilemap_entry(
                                        target=encoding_target,
                                        tile=index,
                                        palette=0 if encoding_target == "game_boy" else palette,
                                        bank=0,
                                        flip_x=flip_x,
                                        flip_y=flip_y,
                                    )
                                )
                    name = f"game/editor/compiled/{layer['id']}_{cx//chunk_width}_{cy//chunk_height}.map.bin"
                    result[name] = bytes(raw)
                    placements.append(
                        {
                            "path": name,
                            "kind": "native_map_chunk",
                            "layer_id": layer["id"],
                            "chunk_origin": [cx, cy],
                            "width": chunk_width,
                            "height": chunk_height,
                            "source_offset": layer["offset"],
                            "requires_source_scroll_integration": True,
                            "endianness": native["endianness"],
                        }
                    )
                    if attributes:
                        result[name.replace(".map.bin", ".attributes.bin")] = bytes(attributes)
                    if encoding_target == "nes":
                        result[name.replace(".map.bin", ".attributes.bin")] = nes_attribute_table(
                            palette_plane, chunk_width, chunk_height
                        )
    for row in document["assets"]:
        result[f"game/editor/compiled/{row['id']}.asset.bin"] = base64.b64decode(
            row["data_base64"], validate=True
        )
    manifest = {
        "schema_version": "skeleton.console_native_asset_projection.v1",
        "target_id": target,
        "document_digest": _digest(document),
        "placements": placements,
        "palette_slots": palette_slots,
        "tile_indices": [
            {"tileset_id": key[0], "tile": key[1], "native_index": value, "bank": tileset_by[key[0]]["bank"]}
            for key, value in indices.items()
        ],
        "baked_transform_count": len(baked),
        "physical_execution_verified": False,
        "source_integration_required": True,
    }
    return result, manifest


def native_source_files(project: ConsoleProject) -> dict[str, str]:
    """Actual compiled-intent C/RGBDS byte tables; source inclusion is explicit."""
    if not isinstance(project, ConsoleProject):
        raise ConsoleEditorError("editor_project_required", "Validated original project required")
    data, manifest = _native_projection(project.as_dict(), console_profile(project.target_id).as_dict())
    result = {"game/editor/compiled/asset_projection.json": _json(manifest).decode() + "\n"}
    for name, raw in data.items():
        key = hashlib.sha256(name.encode()).hexdigest()[:12]
        symbol = "skl_asset_" + key
        lines = [
            "#ifndef SKL_ASSET_" + key.upper(),
            "#define SKL_ASSET_" + key.upper(),
            "/* Original authored data; " + name + " SHA256 " + hashlib.sha256(raw).hexdigest() + " */",
            f"static const unsigned char {symbol}[{len(raw)}] = {{",
        ]
        lines.extend(
            "  " + ",".join(str(value) for value in raw[offset : offset + 16]) + ","
            for offset in range(0, len(raw), 16)
        )
        lines.extend(("};", f"#define {symbol.upper()}_BYTES {len(raw)}", "#endif"))
        header = name.removesuffix(".bin") + ".h"
        result[header] = "\n".join(lines) + "\n"
        if project.target_id in {"game_boy", "game_boy_color", "game_boy_pocket", "game_boy_light"}:
            assembly = [
                "; Original authored data: " + name,
                "; Include in an explicitly selected RGBDS ROM section.",
                symbol + "::",
            ]
            assembly.extend(
                "    db " + ",".join(f"${value:02x}" for value in raw[offset : offset + 16])
                for offset in range(0, len(raw), 16)
            )
            result[name.removesuffix(".bin") + ".inc"] = "\n".join(assembly) + "\n"
    return _files(result)


def _starter_plan(project: ConsoleProject) -> dict:
    document = project.as_dict()
    target = project.target_id
    if target not in {"nes", "game_boy"}:
        raise ConsoleEditorError(
            "editor_native_starter_unavailable",
            "Automatic starter source binding is implemented only forNES andDMG GameBoy",
        )
    if document["config"]["movement_mode"] != "top_down":
        raise ConsoleEditorError(
            "editor_native_starter_mode", "Native starter supports the declared bounded topdown control model"
        )
    width, height = (32, 30) if target == "nes" else (32, 32)
    visible = [layer for layer in document["layers"] if layer["visible"]]
    if len(visible) != 1 or len(document["layers"]) != 1:
        raise ConsoleEditorError(
            "editor_native_starter_layers",
            "Native starter binds one complete background/collision plane; additional layers need an explicit source port",
        )
    layer = visible[0]
    if layer["width"] > width or layer["height"] > height or layer["offset"] != [0.0, 0.0]:
        raise ConsoleEditorError(
            "editor_native_starter_map",
            "Native starter requires one bounded hardware tile map withzero origin; largerworld streaming remains explicit source integration",
        )
    if any(
        row["width"] != 8
        or row["height"] != 8
        or type(row["x"]) not in (int, float)
        or row["x"] != int(row["x"])
        or row["y"] != int(row["y"])
        or not 0 <= row["x"] <= layer["width"] * 8 - 8
        or not 0 <= row["y"] <= layer["height"] * 8 - 8
        for row in document["entities"]
    ):
        raise ConsoleEditorError(
            "editor_native_starter_entities",
            "Native starter binds integer8x8 sprite positions within physical viewport",
        )
    maximum = 64 if target == "nes" else 40
    if len(document["entities"]) > maximum:
        raise ConsoleEditorError(
            "editor_native_starter_sprites", "Authored entities exceed native OAM capacity"
        )
    assets, projection = _native_projection(document, console_profile(target).as_dict())
    names = next((raw for path, raw in assets.items() if path.endswith(".map.bin")), None)
    attrs = next((raw for path, raw in assets.items() if path.endswith(".attributes.bin")), b"")
    patterns = assets.get("game/editor/compiled/bank_0.patterns.bin")
    if names is None or patterns is None:
        raise ConsoleEditorError("editor_native_starter_data", "Native background plane/patternbank required")
    if any(row["bank"] != 0 for row in document["tilesets"]):
        raise ConsoleEditorError(
            "editor_native_starter_bank", "Starter data uses one bound background pattern bank"
        )
    palette = bytearray(assets["game/editor/compiled/palettes.bin"])
    first = document["palettes"][0]["colors"]
    if len(first) != 4:
        raise ConsoleEditorError(
            "editor_native_starter_palette", "Native2bpp starter palette requires exactly4colors"
        )
    sprite_tiles = []
    actors = []
    for row in document["entities"]:
        if row["asset_id"] is not None:
            asset = next(asset for asset in document["assets"] if asset["id"] == row["asset_id"])
            raw = base64.b64decode(asset["data_base64"], validate=True)
            if asset["codec"] == "png":
                iw, ih, pixels = decode_png(raw)
            elif asset["codec"] == "rgba8888":
                iw, ih, pixels = asset["metadata"]["width"], asset["metadata"]["height"], raw
            elif asset["codec"] == "ps1_tim":
                image = decode_tim(raw)
                iw, ih, pixels = image.width, image.height, image.rgba_bytes()
            else:
                raise ConsoleEditorError(
                    "editor_native_starter_sprite", "Sprite requires an original measured image asset"
                )
            if iw != 8 or ih != 8:
                raise ConsoleEditorError(
                    "editor_native_starter_sprite",
                    "Starter sprite art must be exactly8x8; no silent resizing",
                )
            converted, _ = image_to_tiles(pixels, 8, 8, first, "nes_2bpp" if target == "nes" else "gb_2bpp")
            tile = converted[0]
        else:
            # Original procedural glyphs, with transparent native index0.
            kind = row["kind"]
            tile = tuple(
                (
                    (3 if x in (2, 5) and y == 2 else 2 if (x - 3.5) ** 2 + (y - 3.5) ** 2 < 9 else 0)
                    if kind == "player"
                    else (
                        (3 if x == y or x == 7 - y else 0)
                        if kind == "goal"
                        else (
                            (2 if y >= 3 and x in (2, 3, 4, 5) else 1 if y == 2 and x in (3, 4) else 0)
                            if kind == "crop"
                            else (
                                (2 if x in (1, 6) or y in (1, 6) else 1)
                                if kind == "water"
                                else (3 if 1 < x < 6 and 1 < y < 6 else 0)
                            )
                        )
                    )
                )
                for y in range(8)
                for x in range(8)
            )
        index = len(sprite_tiles)
        sprite_tiles.append(tile)
        actors.append(
            {"id": row["id"], "kind": row["kind"], "x": int(row["x"]), "y": int(row["y"]), "tile": index}
        )
    player = next(row for row in actors if row["kind"] == "player")
    goals = [row for row in actors if row["kind"] == "goal"]
    if len(goals) != 1:
        raise ConsoleEditorError(
            "editor_native_starter_goal", "Playable native starter requires exactlyone authored goal marker"
        )
    goal = goals[0]
    if target == "game_boy" and len(patterns) // 16 + len(sprite_tiles) > 256:
        raise ConsoleEditorError(
            "editor_native_starter_capacity",
            "Background+original sprite tiles exceed unsignedDMG256tile address capacity",
        )
    sprite_bytes = encode_tiles(sprite_tiles, "nes_2bpp" if target == "nes" else "gb_2bpp")
    collisions = bytearray(32 * (30 if target == "nes" else 32))
    codes = {"none": 0, "solid": 1, "one_way": 1, "hazard": 2, "goal": 4, "water": 0}
    for y in range(layer["height"]):
        for x in range(layer["width"]):
            collisions[y * 32 + x] = codes[layer["cells"][y * layer["width"] + x]["collision"]]
    bg = bytes(patterns)
    sprite_offset = 0 if target == "nes" else len(bg) // 16
    if target == "nes":
        if len(bg) > 4096 or len(sprite_bytes) > 4096:
            raise ConsoleEditorError(
                "editor_native_starter_capacity", "NROM background/sprite banks exceed4KiB each"
            )
        bg += bytes(4096 - len(bg))
        sprite_bytes += bytes(4096 - len(sprite_bytes))
        palette += bytes(16 - len(palette))
        normal = encode_palette(first, "nes_palette_indices")
        alternate = bytes([normal[0], normal[3], normal[1], normal[2]])
        palette.extend(normal + alternate + normal + alternate)
    else:
        palette = bytearray(
            [sum(value << (2 * index) for index, value in enumerate(encode_palette(first, "dmg_gray")))]
        )
    return {
        "target": target,
        "document_digest": project.digest,
        "player": player,
        "goal": goal,
        "actors": actors,
        "patterns": bg,
        "sprites": sprite_bytes,
        "sprite_offset": sprite_offset,
        "nametable": names + attrs if target == "nes" else names,
        "collisions": bytes(collisions),
        "palette": bytes(palette),
        "speed": max(1, min(8, round(document["config"]["speed"] / 60))),
        "health": next(
            row["properties"]["health"] for row in document["entities"] if row["kind"] == "player"
        ),
        "max_x": layer["width"] * 8 - 8,
        "max_y": layer["height"] * 8 - 8,
        "max_camera_x": max(0, layer["width"] * 8 - 160),
        "max_camera_y": max(0, layer["height"] * 8 - 144),
        "camera_follow": document["config"]["camera_follow"],
        "deferred": ["farming", "fishing", "NPCquests", "hardwaremusic", "scene_graph"]
        + (["scrolling"] if target == "nes" else ["larger_than_32x32_map_streaming"]),
        "projection_digest": _digest(projection),
    }


def _nes_starter_kernel() -> str:
    return """; Original trusted console-editor NROM prototype. Typeddata is inassets.inc.
.segment "HEADER"
.byte "NES", $1A, 2, 1, 0, 0
.res 8,0
.segment "ZEROPAGE"
PlayerX: .res 1
PlayerY: .res 1
NextX: .res 1
NextY: .res 1
Buttons: .res 1
Won: .res 1
Health: .res 1
DamageTimer: .res 1
Col: .res 1
Row: .res 1
Ptr: .res 2
Temp: .res 1
.segment "CODE"
Reset:
 sei
 cld
 ldx #$40
 stx $4017
 ldx #$ff
 txs
 inx
 stx $2000
 stx $2001
 stx $4010
@wait1:
 bit $2002
 bpl @wait1
 ldx #0
 lda #$ff
@clear:
 sta $0200,x
 inx
 bne @clear
 ldx #0
@staticSprites:
 lda SpritePositions,x
 sta $0200,x
 inx
 bne @staticSprites
 lda #INIT_X
 sta PlayerX
 lda #INIT_Y
 sta PlayerY
 lda #INIT_HEALTH
 sta Health
 lda #0
 sta Won
 sta DamageTimer
@wait2:
 bit $2002
 bpl @wait2
 lda #$3f
 sta $2006
 lda #0
 sta $2006
 ldx #0
@palette:
 lda Colors,x
 sta $2007
 inx
 cpx #32
 bne @palette
 lda #<NameTable
 sta Ptr
 lda #>NameTable
 sta Ptr+1
 lda #$20
 sta $2006
 lda #0
 sta $2006
 ldx #4
 ldy #0
@names:
 lda (Ptr),y
 sta $2007
 iny
 bne @names
 inc Ptr+1
 dex
 bne @names
 lda #$08
 sta $2000
 lda #$1e
 sta $2001
Loop:
 bit $2002
 bpl Loop
 jsr PollPad
 lda Health
 beq @frozen
 jsr Movement
 jsr CheckGoal
@frozen:
 jsr Sprites
 lda #0
 sta $2003
 lda #2
 sta $4014
 lda #0
 sta $2005
 sta $2005
 lda #$08
 sta $2000
@visible:
 bit $2002
 bmi @visible
 jmp Loop
PollPad:
 lda #1
 sta $4016
 lda #0
 sta $4016
 sta Buttons
 ldx #8
@read:
 lda $4016
 lsr a
 rol Buttons
 dex
 bne @read
 rts
Movement:
 lda PlayerX
 sta NextX
 lda PlayerY
 sta NextY
 lda Buttons
 and #1
 beq @left
 lda PlayerX
 clc
 adc #STEP
 bcs @left
 sta NextX
 jsr CanMove
 bcs @left
 lda NextX
 sta PlayerX
@left:
 lda PlayerX
 sta NextX
 lda Buttons
 and #2
 beq @down
 lda PlayerX
 sec
 sbc #STEP
 bcc @down
 sta NextX
 jsr CanMove
 bcs @down
 lda NextX
 sta PlayerX
@down:
 lda PlayerX
 sta NextX
 lda Buttons
 and #4
 beq @up
 lda PlayerY
 clc
 adc #STEP
 bcs @up
 sta NextY
 jsr CanMove
 bcs @up
 lda NextY
 sta PlayerY
@up:
 lda PlayerY
 sta NextY
 lda Buttons
 and #8
 beq @done
 lda PlayerY
 sec
 sbc #STEP
 bcc @done
 sta NextY
 jsr CanMove
 bcs @done
 lda NextY
 sta PlayerY
@done:
 rts
CanMove:
 lda NextX
 cmp #MAX_X+1
 bcs @blocked
 lda NextY
 cmp #MAX_Y+1
 bcs @blocked
 lda NextX
 ldx NextY
 jsr GetCollision
 and #1
 bne @blocked
 lda NextX
 clc
 adc #7
 ldx NextY
 jsr GetCollision
 and #1
 bne @blocked
 lda NextY
 clc
 adc #7
 tax
 lda NextX
 jsr GetCollision
 and #1
 bne @blocked
 lda NextY
 clc
 adc #7
 tax
 lda NextX
 clc
 adc #7
 jsr GetCollision
 and #1
 bne @blocked
 clc
 rts
@blocked:
 sec
 rts
GetCollision:
 lsr a
 lsr a
 lsr a
 sta Col
 txa
 lsr a
 lsr a
 lsr a
 sta Row
 and #7
 asl a
 asl a
 asl a
 asl a
 asl a
 sta Ptr
 lda Row
 lsr a
 lsr a
 lsr a
 sta Ptr+1
 lda Ptr
 clc
 adc #<Collision
 sta Ptr
 lda Ptr+1
 adc #>Collision
 sta Ptr+1
 ldy Col
 lda (Ptr),y
 rts
CheckGoal:
 lda PlayerX
 sec
 sbc #GOAL_X
 bcs @positiveX
 eor #$ff
 clc
 adc #1
@positiveX:
 cmp #8
 bcs @damage
 lda PlayerY
 sec
 sbc #GOAL_Y
 bcs @positiveY
 eor #$ff
 clc
 adc #1
@positiveY:
 cmp #8
 bcs @damage
 lda #1
 sta Won
@damage:
 lda DamageTimer
 beq @check
 dec DamageTimer
 rts
@check:
 lda PlayerY
 clc
 adc #4
 tax
 lda PlayerX
 clc
 adc #4
 jsr GetCollision
 sta Temp
 and #4
 beq @hazard
 lda #1
 sta Won
@hazard:
 lda Temp
 and #2
 beq @end
 dec Health
 lda #30
 sta DamageTimer
@end:
 rts
Sprites:
 lda PlayerY
 sec
 sbc #1
 sta $0200+PLAYER_OAM
 lda PlayerX
 sta $0203+PLAYER_OAM
 lda Won
 sta $0202+PLAYER_OAM
 rts
NMI: rti
IRQ: rti
.include "assets.inc"
.segment "VECTORS"
.addr NMI,Reset,IRQ
"""


def _gb_starter_kernel() -> str:
    return """; Original trusted DMG editor prototype. Originaldata is inassets.inc.
DEF rJOYP EQU $FF00
DEF rLCDC EQU $FF40
DEF rLY EQU $FF44
DEF rBGP EQU $FF47
DEF rOBP0 EQU $FF48
DEF rSCX EQU $FF43
DEF rSCY EQU $FF42
SECTION "Entry",ROM0[$100]
 jp Start
 ds $150-@,0
SECTION "Game",ROM0[$150]
Start:
 di
 ld sp,$FFFE
 ldh a,[rLCDC]
 bit 7,a
 jr z,.off
.wait:
 ldh a,[rLY]
 cp 144
 jr c,.wait
.off:
 xor a
 ldh [rLCDC],a
 ldh [rSCX],a
 ldh [rSCY],a
 ld hl,$8000
 ld bc,$2000
.clearVRAM:
 xor a
 ld [hli],a
 dec bc
 ld a,b
 or c
 jr nz,.clearVRAM
 ld hl,$FE00
 ld b,160
.clearOAM:
 ld [hli],a
 dec b
 jr nz,.clearOAM
 ld hl,$8000
 ld de,Tiles
 ld bc,TilesEnd-Tiles
 call Copy
 ld hl,$9800
 ld de,NameTable
 ld bc,1024
 call Copy
 ld hl,ShadowOAM
 ld b,160
 xor a
.clearShadow:
 ld [hli],a
 dec b
 jr nz,.clearShadow
 ld hl,$FF80
 ld de,DmaRoutine
 ld bc,DmaRoutineEnd-DmaRoutine
 call Copy
 ld a,INIT_X
 ld [PlayerX],a
 ld a,INIT_Y
 ld [PlayerY],a
 ld a,INIT_HEALTH
 ld [Health],a
 xor a
 ld [Won],a
 ld [DamageTimer],a
 ld [CameraX],a
 ld [CameraY],a
 ld a,BGP_VALUE
 ldh [rBGP],a
 ldh [rOBP0],a
 call BuildSprites
 call UploadFrame
 ld a,$93
 ldh [rLCDC],a
.loop:
 call PollPad
 ld a,[Health]
 and a
 jr z,.frozen
 call Movement
 call CheckGoal
.frozen:
 call BuildSprites
 call WaitFrame
 call UploadFrame
 jr .loop
Copy:
 ld a,[de]
 ld [hli],a
 inc de
 dec bc
 ld a,b
 or c
 jr nz,Copy
 ret
WaitFrame:
 ldh a,[rLY]
 cp 144
 jr nc,WaitFrame
.wait:
 ldh a,[rLY]
 cp 144
 jr c,.wait
 ret
PollPad:
 ld a,$20
 ldh [rJOYP],a
 ldh a,[rJOYP]
 ldh a,[rJOYP]
 cpl
 and $0F
 ld [Buttons],a
 ld a,$30
 ldh [rJOYP],a
 ret
Movement:
 ld a,[PlayerX]
 ld [NextX],a
 ld a,[PlayerY]
 ld [NextY],a
 ld a,[Buttons]
 bit 0,a
 jr z,.left
 ld a,[PlayerX]
 add STEP
 jr c,.left
 ld [NextX],a
 call CanMove
 jr nz,.left
 ld a,[NextX]
 ld [PlayerX],a
.left:
 ld a,[PlayerX]
 ld [NextX],a
 ld a,[Buttons]
 bit 1,a
 jr z,.up
 ld a,[PlayerX]
 sub STEP
 jr c,.up
 ld [NextX],a
 call CanMove
 jr nz,.up
 ld a,[NextX]
 ld [PlayerX],a
.up:
 ld a,[PlayerX]
 ld [NextX],a
 ld a,[Buttons]
 bit 2,a
 jr z,.down
 ld a,[PlayerY]
 sub STEP
 jr c,.down
 ld [NextY],a
 call CanMove
 jr nz,.down
 ld a,[NextY]
 ld [PlayerY],a
.down:
 ld a,[PlayerY]
 ld [NextY],a
 ld a,[Buttons]
 bit 3,a
 jr z,.end
 ld a,[PlayerY]
 add STEP
 jr c,.end
 ld [NextY],a
 call CanMove
 jr nz,.end
 ld a,[NextY]
 ld [PlayerY],a
.end:
 ret
CanMove:
 ld a,[NextX]
 cp MAX_X+1
 jr nc,.blocked
 ld a,[NextY]
 cp MAX_Y+1
 jr nc,.blocked
 ld b,a
 ld a,[NextX]
 call GetCollision
 bit 0,a
 jr nz,.blocked
 ld a,[NextY]
 ld b,a
 ld a,[NextX]
 add 7
 call GetCollision
 bit 0,a
 jr nz,.blocked
 ld a,[NextY]
 add 7
 ld b,a
 ld a,[NextX]
 call GetCollision
 bit 0,a
 jr nz,.blocked
 ld a,[NextY]
 add 7
 ld b,a
 ld a,[NextX]
 add 7
 call GetCollision
 bit 0,a
 jr nz,.blocked
 xor a
 ret
.blocked:
 ld a,1
 and a
 ret
GetCollision:
 ld c,a
 ld a,b
 srl a
 srl a
 srl a
 ld l,a
 ld h,0
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,hl
 ld a,c
 srl a
 srl a
 srl a
 ld e,a
 ld d,0
 add hl,de
 ld de,Collision
 add hl,de
 ld a,[hl]
 ret
CheckGoal:
 ld a,[PlayerX]
 sub GOAL_X
 jr nc,.positiveX
 cpl
 inc a
.positiveX:
 cp 8
 jr nc,.damage
 ld a,[PlayerY]
 sub GOAL_Y
 jr nc,.positiveY
 cpl
 inc a
.positiveY:
 cp 8
 jr nc,.damage
 ld a,1
 ld [Won],a
.damage:
 ld a,[DamageTimer]
 and a
 jr z,.check
 dec a
 ld [DamageTimer],a
 ret
.check:
 ld a,[PlayerY]
 add 4
 ld b,a
 ld a,[PlayerX]
 add 4
 call GetCollision
 ld b,a
 bit 2,b
 jr z,.hazard
 ld a,1
 ld [Won],a
.hazard:
 bit 1,b
 ret z
 ld a,[Health]
 dec a
 ld [Health],a
 ld a,30
 ld [DamageTimer],a
 ret
; Prepare sprites in ordinary WRAM during visible scanlines. Only the
; copied HRAM DMA routine touches native OAM during vblank.
BuildSprites:
 ld a,CAMERA_FOLLOW
 and a
 jr z,.cameraDone
 ld a,[PlayerX]
 sub 80
 jr nc,.positiveX
 xor a
.positiveX:
 cp MAX_CAMERA_X+1
 jr c,.storeX
 ld a,MAX_CAMERA_X
.storeX:
 ld [CameraX],a
 ld a,[PlayerY]
 sub 72
 jr nc,.positiveY
 xor a
.positiveY:
 cp MAX_CAMERA_Y+1
 jr c,.storeY
 ld a,MAX_CAMERA_Y
.storeY:
 ld [CameraY],a
.cameraDone:
 ld hl,ShadowOAM
 ld de,SpritePositions
 ld b,ACTOR_COUNT
.actor:
 ld a,[de]
 inc de
 ld [SpriteY],a
 ld a,[de]
 inc de
 ld [SpriteX],a
 ld a,l
 cp PLAYER_OAM
 jr nz,.static
 ld a,[PlayerY]
 ld [SpriteY],a
 ld a,[PlayerX]
 ld [SpriteX],a
.static:
 ld a,[CameraY]
 ld c,a
 ld a,[SpriteY]
 sub c
 jr c,.hidden
 cp 144
 jr nc,.hidden
 add 16
 ld [hl],a
 ld a,[CameraX]
 ld c,a
 ld a,[SpriteX]
 sub c
 jr c,.hidden
 cp 160
 jr nc,.hidden
 add 8
 inc hl
 ld [hli],a
 jr .art
.hidden:
 xor a
 ld [hli],a
 ld [hli],a
.art:
 ld a,[de]
 inc de
 ld [hli],a
 ld a,[de]
 inc de
 ld [hli],a
 dec b
 jr nz,.actor
 ret
UploadFrame:
 ld a,[CameraX]
 ldh [rSCX],a
 ld a,[CameraY]
 ldh [rSCY],a
 call $FF80
 ld a,[Won]
 and a
 ld a,BGP_VALUE
 jr z,.palette
 xor $FF
.palette:
 ldh [rOBP0],a
 ret
DmaRoutine:
 ld a,HIGH(ShadowOAM)
 ldh [$FF46],a
 ld a,40
.wait:
 dec a
 jr nz,.wait
 ret
DmaRoutineEnd:

INCLUDE "assets.inc"
SECTION "Variables",WRAM0
PlayerX: ds 1
PlayerY: ds 1
NextX: ds 1
NextY: ds 1
Buttons: ds 1
Won: ds 1
Health: ds 1
DamageTimer: ds 1
CameraX: ds 1
CameraY: ds 1
SpriteX: ds 1
SpriteY: ds 1
SECTION "Shadow OAM",WRAM0,ALIGN[8]
ShadowOAM: ds 160
"""


def native_starter_source_files(project: ConsoleProject) -> dict[str, str]:
    """Exact playable original ROM source bound to authored pixels/maps/palettes."""
    plan = _starter_plan(project)
    target = plan["target"]
    prefix = f"game/generated/native/{target}/"
    player, goal = plan["player"], plan["goal"]
    player_index = next(index for index, row in enumerate(plan["actors"]) if row["id"] == player["id"])
    constants = {
        "INIT_X": player["x"],
        "INIT_Y": player["y"],
        "GOAL_X": goal["x"],
        "GOAL_Y": goal["y"],
        "MAX_X": plan["max_x"],
        "MAX_Y": plan["max_y"],
        "INIT_HEALTH": plan["health"],
        "STEP": plan["speed"],
        "PLAYER_OAM": player_index * 4,
        "ACTOR_BYTES": len(plan["actors"]) * 4,
        "ACTOR_COUNT": len(plan["actors"]),
        "MAX_CAMERA_X": plan["max_camera_x"],
        "MAX_CAMERA_Y": plan["max_camera_y"],
        "CAMERA_FOLLOW": int(plan["camera_follow"]),
    }
    positions = bytearray()
    for row in plan["actors"]:
        if target == "nes":
            positions.extend(((row["y"] - 1) & 255, row["tile"], 0, row["x"]))
        else:
            positions.extend((row["y"], row["x"], row["tile"] + plan["sprite_offset"], 0))
    kernel = _nes_starter_kernel() if target == "nes" else _gb_starter_kernel()
    lines = ["; Generated original editordata. SHA256 " + project.digest]
    lines.extend(
        (f"{key} = {value}" if target == "nes" else f"DEF {key} EQU {value}")
        for key, value in constants.items()
    )

    def array(label, raw):
        lines.append(label + (":" if target == "nes" else "::"))
        lines.extend(
            (" .byte " if target == "nes" else " db ")
            + ",".join(f"${value:02x}" for value in raw[offset : offset + 16])
            for offset in range(0, len(raw), 16)
        )

    if target == "nes":
        lines.append('.segment "CODE"')
        array("Colors", plan["palette"])
        array("NameTable", plan["nametable"])
        array("Collision", plan["collisions"])
        array("SpritePositions", positions + bytes([255]) * (256 - len(positions)))
        lines.append('.segment "CHARS"')
        array("BackgroundPatterns", plan["patterns"])
        array("OriginalSprites", plan["sprites"])
        cfg = """MEMORY {
 HEADER: start=$0000,size=$0010,type=ro,file=%O;
 ZP: start=$0000,size=$0100,type=rw;
 RAM: start=$0200,size=$0600,type=rw;
 PRG: start=$8000,size=$7FFA,type=ro,file=%O,fill=yes;
 VEC: start=$FFFA,size=$0006,type=ro,file=%O;
 CHR: start=$0000,size=$2000,type=ro,file=%O,fill=yes;
}
SEGMENTS {
 HEADER: load=HEADER,type=ro;
 ZEROPAGE: load=ZP,type=zp;
 BSS: load=RAM,type=bss;
 CODE: load=PRG,type=ro;
 VECTORS: load=VEC,type=ro;
 CHARS: load=CHR,type=ro;
}
"""
        result = {
            prefix + "src/main.s": kernel,
            prefix + "nes.cfg": cfg,
            prefix + "assets.inc": "\n".join(lines) + "\n",
        }
    else:
        lines.append(f'DEF BGP_VALUE EQU ${plan["palette"][0]:02x}')
        array("Tiles", plan["patterns"] + plan["sprites"])
        lines.append("TilesEnd::")
        array("NameTable", plan["nametable"])
        array("Collision", plan["collisions"])
        array("SpritePositions", positions)
        result = {prefix + "src/main.asm": kernel, prefix + "assets.inc": "\n".join(lines) + "\n"}
    binding = {
        "schema_version": "skeleton.console_editor_native_binding.v1",
        "target_id": target,
        "document_digest": project.digest,
        "kernel_path": prefix + ("src/main.s" if target == "nes" else "src/main.asm"),
        "kernel_sha256": hashlib.sha256(kernel.encode()).hexdigest(),
        "assets_path": prefix + "assets.inc",
        "assets_sha256": hashlib.sha256(result[prefix + "assets.inc"].encode()).hexdigest(),
        "profile_digest": project.as_dict()["profile_digest"],
        "scope": (
            "bounded_native_32x32_world_movement_collision_goal_scroll_dma"
            if target == "game_boy"
            else "bounded_native_tile_scene_movement_collision_goal"
        ),
        "deferred_mechanics": plan["deferred"],
        "movement_quantization": {
            "requested_pixels_per_nominal_second": project.as_dict()["config"]["speed"],
            "actual_pixels_per_frame": plan["speed"],
            "actual_core_fps_unavailable_until_execution": True,
        },
        "binary_build_verified": False,
        "native_execution_verified": False,
    }
    result["game/editor/native_binding.json"] = _json(binding).decode() + "\n"
    return _files(result)


def _native_binding_status(project: ConsoleProject) -> dict:
    raw = project._files.get("game/editor/native_binding.json")
    if raw is None:
        return {"bound": False, "code": "native_starter_not_bound", "source_integration_required": True}
    binding = _load(raw, 8192)
    required = {
        "schema_version",
        "target_id",
        "document_digest",
        "kernel_path",
        "kernel_sha256",
        "assets_path",
        "assets_sha256",
        "profile_digest",
        "scope",
        "deferred_mechanics",
        "movement_quantization",
        "binary_build_verified",
        "native_execution_verified",
    }
    if (
        set(binding) != required
        or binding["schema_version"] != "skeleton.console_editor_native_binding.v1"
        or binding["target_id"] != project.target_id
    ):
        raise ConsoleEditorError("editor_native_binding_corrupt", "Native binding schema or target differs")
    try:
        expected = native_starter_source_files(project)
    except (ConsoleEditorError, ConsoleAssetError) as exc:
        return {
            "bound": False,
            "code": getattr(exc, "code", "native_starter_unavailable"),
            "message": str(exc),
            "source_integration_required": True,
        }
    graph_active = any(
        project.scene_graph.as_dict()[key] for key in ("nodes", "animations", "rules", "variables")
    )
    valid = (
        not graph_active
        and binding["document_digest"] == project.digest
        and binding["profile_digest"] == project.as_dict()["profile_digest"]
        and all(project._files.get(name) == text for name, text in expected.items())
    )
    return {
        **binding,
        "bound": valid,
        "code": (
            "scene_graph_requires_native_source_port"
            if graph_active
            else "source_data_bound" if valid else "source_modified_or_stale"
        ),
        "source_integration_required": not valid,
        "binary_build_verified": False,
        "native_execution_verified": False,
    }


def inspect_console_project(
    project: ConsoleProject | Mapping[str, str], *, include_reachability: bool = True
) -> dict:
    """Measured static editor facts; this never invents game/hardware quality."""
    from collections import Counter, deque

    if type(include_reachability) is not bool:
        raise ConsoleEditorError("editor_review_invalid", "Reachability option must be a boolean")
    if isinstance(project, Mapping):
        project = ConsoleProject.from_files(project)
    if not isinstance(project, ConsoleProject):
        raise ConsoleEditorError("editor_project_required", "A validated authored project is required")
    document = _document(project.as_dict())
    profile = console_profile(project.target_id).as_dict()
    files = project.export_files()
    tiles = sum(len(row["tiles"]) for row in document["tilesets"])
    cells = sum(len(row["cells"]) for row in document["layers"])
    collisions = Counter(cell["collision"] for layer in document["layers"] for cell in layer["cells"])
    entities = Counter(row["kind"] for row in document["entities"])
    source_bytes = sum(len(text.encode()) for text in files.values())
    asset_bytes = sum(len(base64.b64decode(row["data_base64"], validate=True)) for row in document["assets"])
    checks = [{"id": "scene_graph", "status": "pass", "metrics": project.scene_graph.inspect()}]
    checks += [
        {
            "id": "typed_document",
            "status": "pass",
            "measurement": "Canonical schema, references,finite numbers and originalasset source decoding accepted",
        },
        {
            "id": "file_manifest",
            "status": "pass",
            "metrics": {"files": len(files), "utf8_bytes": source_bytes, "capacity_bytes": MAX_FILE_TOTAL},
        },
        {
            "id": "scene_rules",
            "status": "pass",
            "metrics": {
                "tiles": tiles,
                "map_cells": cells,
                "layers": len(document["layers"]),
                "entities": dict(entities),
                "collision_cells": dict(collisions),
                "audio_cues": len(document["audio"]["cues"]),
                "asset_bytes": asset_bytes,
            },
        },
        {
            "id": "hardware_memory",
            "status": (
                "unavailable"
                if profile["native_constraints"].get("vram_bytes") is None
                else "declared_constraint"
            ),
            "metrics": {
                "vram_bytes": profile["native_constraints"].get("vram_bytes"),
                "pattern_bytes": profile["native_constraints"].get("pattern_bytes"),
                "scope": profile["native_constraints"]["scope"],
            },
        },
    ]
    try:
        binary, projection = _native_projection(document, profile)
        checks.append(
            {
                "id": "native_asset_projection",
                "status": "pass",
                "metrics": {
                    "encoded_bytes": sum(len(data) for data in binary.values()),
                    "files": len(binary),
                    "baked_transform_count": projection["baked_transform_count"],
                    "native_binary_execution_verified": False,
                },
            }
        )
    except (ConsoleEditorError, ConsoleAssetError) as exc:
        checks.append(
            {"id": "native_asset_projection", "status": "blocked", "code": exc.code, "message": str(exc)}
        )
    navigation = {
        "status": "unavailable",
        "scope": "Conservative topdown8pixelgrid static navigation, excluding movingentities,damage budgets,portals and platformer gravity",
    }
    if (
        include_reachability
        and not any(project.scene_graph.as_dict()[key] for key in ("nodes", "animations", "rules"))
        and document["config"]["movement_mode"] == "top_down"
        and len(document["layers"]) == 1
        and document["layers"][0]["offset"] == [0.0, 0.0]
    ):
        layer = document["layers"][0]
        width, height = layer["width"], layer["height"]
        player = next(row for row in document["entities"] if row["kind"] == "player")
        if player["width"] == 8 and player["height"] == 8 and player["x"] % 8 == 0 and player["y"] % 8 == 0:
            start = (int(player["x"] // 8), int(player["y"] // 8))
            blocked = {
                (index % width, index // width)
                for index, cell in enumerate(layer["cells"])
                if cell["collision"] in {"solid", "one_way"}
            }
            for row in document["entities"]:
                if row["kind"] == "platform":
                    for y in range(
                        int(row["y"] // 8), min(height, math.ceil((row["y"] + row["height"]) / 8))
                    ):
                        for x in range(
                            int(row["x"] // 8), min(width, math.ceil((row["x"] + row["width"]) / 8))
                        ):
                            blocked.add((x, y))
            reachable = set()
            queue = (
                deque([start])
                if 0 <= start[0] < width and 0 <= start[1] < height and start not in blocked
                else deque()
            )
            while queue:
                point = queue.popleft()
                if point in reachable:
                    continue
                reachable.add(point)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    candidate = (point[0] + dx, point[1] + dy)
                    if (
                        0 <= candidate[0] < width
                        and 0 <= candidate[1] < height
                        and candidate not in blocked
                        and candidate not in reachable
                    ):
                        queue.append(candidate)
            goals = [row for row in document["entities"] if row["kind"] == "goal"]
            goal_reachability = {
                row["id"]: (int(row["x"] // 8), int(row["y"] // 8)) in reachable for row in goals
            }
            for index, cell in enumerate(layer["cells"]):
                if cell["collision"] == "goal":
                    goal_reachability[f"cell_{index%width}_{index//width}"] = (
                        index % width,
                        index // width,
                    ) in reachable
            navigation.update(
                status="measured_grid",
                reachable_cells=len(reachable),
                total_cells=width * height,
                spawn_blocked=start in blocked,
                goal_reachability=goal_reachability,
            )
    checks.append({"id": "navigation", "status": navigation["status"], "metrics": navigation})
    binding = _native_binding_status(project)
    checks.append(
        {
            "id": "native_source_binding",
            "status": "pass" if binding["bound"] else "unavailable",
            "metrics": binding,
        }
    )
    report = {
        "schema_version": "skeleton.console_editor_review.v1",
        "target_id": project.target_id,
        "document_digest": project.digest,
        "manifest_digest": project.manifest_digest,
        "source_manifest_digest": project.source_manifest_digest,
        "profile_digest": profile["profile_digest"],
        "checks": checks,
        "metrics": {
            "tiles": tiles,
            "map_cells": cells,
            "source_utf8_bytes": source_bytes,
            "asset_bytes": asset_bytes,
            "entities": dict(entities),
            "reachable_cells": navigation.get("reachable_cells"),
            "goal_reachability": navigation.get("goal_reachability"),
            "scene_graph": project.scene_graph.inspect(),
        },
        "validation": project.validate().as_dict(),
        "hardware_emulation": False,
        "native_execution_verified": False,
        "game_quality_measured": False,
        "promotion_authorized": False,
    }
    return {**report, "report_digest": _digest(report)}


@dataclass(frozen=True, slots=True)
class ConsoleEditTransaction:
    """Bounded inversefile patch. Durable history belongs to existingbackend."""

    result: ConsoleEditResult
    before_manifest_digest: str
    after_manifest_digest: str
    inverse_files: Mapping[str, str | None]
    transaction_digest: str

    def as_dict(self, *, include_inverse: bool = False) -> dict:
        if type(include_inverse) is not bool:
            raise ConsoleEditorError("editor_transaction_invalid", "Inverse option must be boolean")
        return {
            "schema_version": "skeleton.console_editor_transaction.v1",
            "before_manifest_digest": self.before_manifest_digest,
            "after_manifest_digest": self.after_manifest_digest,
            "transaction_digest": self.transaction_digest,
            "changes": list(self.result.changes),
            "inverse_files": {
                name: (
                    text
                    if include_inverse
                    else {
                        "present": text is not None,
                        "sha256": None if text is None else hashlib.sha256(text.encode()).hexdigest(),
                    }
                )
                for name, text in self.inverse_files.items()
            },
            "durable_commit_authority": "existing_backend_project_revision_CAS",
        }

    def undo(self, files: Mapping[str, str], *, expected_manifest_digest: str) -> ConsoleEditResult:
        current = _files(files)
        if (
            expected_manifest_digest != self.after_manifest_digest
            or file_manifest_digest(current) != self.after_manifest_digest
        ):
            raise ConsoleEditorError(
                "editor_undo_conflict", "Undo requires the exactpost-transaction filemanifest", 409
            )
        payload = {
            "before": self.before_manifest_digest,
            "after": self.after_manifest_digest,
            "inverse_files": dict(self.inverse_files),
            "project_id": self.result.project.as_dict()["project_id"],
            "target_id": self.result.project.target_id,
        }
        if _digest(payload) != self.transaction_digest:
            raise ConsoleEditorError("editor_transaction_corrupt", "Inverse patch identity differs")
        for name, text in self.inverse_files.items():
            _path(name)
            if text is None:
                current.pop(name, None)
            else:
                current[name] = text
        current = _files(current)
        if file_manifest_digest(current) != self.before_manifest_digest:
            raise ConsoleEditorError(
                "editor_transaction_corrupt", "Inverse does not restore exactsource identity"
            )
        project = ConsoleProject.from_files(current, target_id=self.result.project.target_id)
        if project.as_dict()["project_id"] != self.result.project.as_dict()["project_id"]:
            raise ConsoleEditorError("editor_transaction_foreign", "Undo cannot crossproject identity")
        return ConsoleEditResult(
            MappingProxyType(current),
            self.before_manifest_digest,
            project,
            ({"op": "undo_transaction", "transaction_digest": self.transaction_digest},),
            project.validate(),
        )


def begin_console_edit_transaction(
    files: Mapping[str, str],
    *,
    target_id: str,
    edits: Sequence[Mapping],
    expected_manifest_digest: str,
    project_id: str | None = None,
) -> ConsoleEditTransaction:
    before = _files(files)
    result = apply_console_edits(
        before,
        target_id=target_id,
        edits=edits,
        expected_manifest_digest=expected_manifest_digest,
        project_id=project_id,
    )
    inverse = {
        name: before.get(name)
        for name in before.keys() | result.files.keys()
        if before.get(name) != result.files.get(name)
    }
    payload = {
        "before": file_manifest_digest(before),
        "after": result.manifest_digest,
        "inverse_files": inverse,
        "project_id": result.project.as_dict()["project_id"],
        "target_id": result.project.target_id,
    }
    return ConsoleEditTransaction(
        result, payload["before"], payload["after"], MappingProxyType(inverse), _digest(payload)
    )
