"""Hardware generation envelope — the other era axis.

Gameplay dialects (soulslike, extraction, …) say how a run *plays*.
Hardware generations (8-bit → next-gen) say what the forge is *allowed
to emit*: storage, palette, resolution, poly budget, audio format, file
count. Ported from backend/core/eras.py (the catalog that already had
tests) into the Skeleton compiler so a dialect can sit on a NES cart
or a 4K disc without inventing a third set of numbers.

+40% asset_capacity is the "outshine the era" contract: we respect the
envelope and then exceed the historical usual-max by the documented
margin. Viewport is clamped to a playable window; the envelope
resolution stays on the pack for exporters.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List, Optional, Tuple

_KB = 1024
_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024

GENERATIONS: Dict[str, Dict[str, Any]] = {
    "8bit": {
        "key": "8bit", "order": 0, "label": "8-Bit", "platforms": ["NES", "SMS"],
        "tagline": "Hand-drawn sprites, chiptune, cartridge-tight.",
        "storage_bytes": [8 * _KB, 1 * _MB], "storage_label": "8 KB – 1 MB",
        "max_sprites": 64, "sprite_dim": "8x8", "max_poly": 0,
        "poly_label": "2D · no polygons", "colors_max": 64,
        "color_label": "25–64 colors", "resolution": "256x240",
        "audio_format": "Chiptune synth", "audio_kb_range": [1, 5],
        "asset_kb_range": [1, 32],
        "asset_types": ["sprite_sheet", "icon", "thumbnail", "sfx", "palette_swatch"],
        "texture_res": "8x8–32x32 indexed",
    },
    "16bit": {
        "key": "16bit", "order": 1, "label": "16-Bit", "platforms": ["SNES", "Genesis"],
        "tagline": "Bigger sprites, compressed PCM, Mode-7 dreams.",
        "storage_bytes": [512 * _KB, 6 * _MB], "storage_label": "512 KB – 6 MB",
        "max_sprites": 128, "sprite_dim": "64x64", "max_poly": 0,
        "poly_label": "2D · no polygons", "colors_max": 512,
        "color_label": "256–512 colors", "resolution": "320x224",
        "audio_format": "Compressed 8-bit PCM", "audio_kb_range": [5, 64],
        "asset_kb_range": [8, 128],
        "asset_types": ["sprite_sheet", "icon", "thumbnail", "anim_clip", "sfx", "vfx", "palette_swatch"],
        "texture_res": "up to 64x64 indexed",
    },
    "early3d": {
        "key": "early3d", "order": 2, "label": "Early 3D", "platforms": ["PS1", "N64", "Saturn"],
        "tagline": "Polygons arrive — low-res textures, MIDI & ADPCM.",
        "storage_bytes": [12 * _MB, 650 * _MB], "storage_label": "12 MB – 650 MB",
        "max_sprites": 0, "sprite_dim": "—", "max_poly": 3000,
        "poly_label": "300–3,000 polys / model", "colors_max": 65536,
        "color_label": "16-bit color", "resolution": "320x240–640x480",
        "audio_format": "Sequenced MIDI & 11–32kHz", "audio_kb_range": [16, 512],
        "asset_kb_range": [64, 4096],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "64x64–256x256",
    },
    "64bit": {
        "key": "64bit", "order": 3, "label": "64-Bit / DVD", "platforms": ["PS2", "Xbox", "GameCube"],
        "tagline": "DVD-scale worlds, true-color, Dolby Pro Logic.",
        "storage_bytes": [int(1.4 * _GB), int(4.7 * _GB)], "storage_label": "1.4 GB – 4.7 GB",
        "max_sprites": 0, "sprite_dim": "—", "max_poly": 10000,
        "poly_label": "3,000–10,000 polys / model", "colors_max": 16777216,
        "color_label": "24-bit color", "resolution": "480i–480p",
        "audio_format": "ADPCM Dolby Pro Logic", "audio_kb_range": [256, 8192],
        "asset_kb_range": [256, 32768],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "256x256–512x512",
    },
    "earlyhd": {
        "key": "earlyhd", "order": 4, "label": "Early HD", "platforms": ["PS3", "Xbox 360"],
        "tagline": "Normal maps, dynamic lighting, 5.1 surround.",
        "storage_bytes": [int(8.5 * _GB), 50 * _GB], "storage_label": "8.5 GB – 50 GB",
        "max_sprites": 0, "sprite_dim": "—", "max_poly": 50000,
        "poly_label": "10,000–50,000 polys / model", "colors_max": 16777216,
        "color_label": "true-color HD", "resolution": "720p–1080p",
        "audio_format": "Uncompressed 5.1 Surround", "audio_kb_range": [2048, 65536],
        "asset_kb_range": [1024, 262144],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "1024x1024–2048x2048",
    },
    "modern": {
        "key": "modern", "order": 5, "label": "Modern", "platforms": ["PS5", "Xbox Series", "PC"],
        "tagline": "4K textures, photogrammetry, real-time ray tracing.",
        "storage_bytes": [50 * _GB, 150 * _GB], "storage_label": "50 GB – 150 GB+",
        "max_sprites": 0, "sprite_dim": "—", "max_poly": 10_000_000,
        "poly_label": "Millions of polys (Nanite/Virtual)", "colors_max": 1_073_741_824,
        "color_label": "10-bit HDR / 4K", "resolution": "2160p (4K)",
        "audio_format": "Spatial 3D audio (Atmos)", "audio_kb_range": [16384, 524288],
        "asset_kb_range": [8192, 2_097_152],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "4096x4096 (4K)",
    },
    "nextgen": {
        "key": "nextgen", "order": 6, "label": "Next-Gen", "platforms": ["PS6?", "Next Xbox", "PC"],
        "tagline": "8K textures, path tracing, object-based 3D audio.",
        "storage_bytes": [250 * _GB, 500 * _GB], "storage_label": "250 GB – 500 GB",
        "max_sprites": 0, "sprite_dim": "—", "max_poly": 100_000_000,
        "poly_label": "Billions virtualized (micropoly)", "colors_max": 1_073_741_824,
        "color_label": "12-bit HDR / 8K", "resolution": "4320p (8K)",
        "audio_format": "Object-based 3D audio (path-traced)", "audio_kb_range": [65536, 1_048_576],
        "asset_kb_range": [16384, 8_388_608],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "8192x8192 (8K)",
    },
}

_USUAL_MAX_ASSETS = {
    "8bit": 1_000, "16bit": 4_000, "early3d": 15_000, "64bit": 60_000,
    "earlyhd": 250_000, "modern": 1_000_000, "nextgen": 4_000_000,
}
_FILE_COUNT_STANDARD = {
    "8bit": 200, "16bit": 1_200, "early3d": 3_500, "64bit": 12_000,
    "earlyhd": 45_000, "modern": 250_000, "nextgen": 600_000,
}
_VIEWPORT = {
    "8bit": (256, 240), "16bit": (320, 224), "early3d": (640, 480),
    "64bit": (640, 480), "earlyhd": (1280, 720), "modern": (1280, 720),
    "nextgen": (1280, 720),
}
for _k, _spec in GENERATIONS.items():
    _usual = _USUAL_MAX_ASSETS[_k]
    _spec["usual_max_assets"] = _usual
    _spec["asset_capacity"] = round(_usual * 1.4)
    _spec["outshine_pct"] = 40
    _spec["file_count_standard"] = _FILE_COUNT_STANDARD[_k]
    _spec["viewport"] = list(_VIEWPORT[_k])

GEN_ORDER: List[str] = sorted(GENERATIONS, key=lambda k: GENERATIONS[k]["order"])
DEFAULT_GENERATION = "modern"

_ALIAS = {
    "8bit": "8bit", "8": "8bit", "nes": "8bit", "famicom": "8bit", "sms": "8bit",
    "16bit": "16bit", "16": "16bit", "snes": "16bit", "genesis": "16bit", "megadrive": "16bit",
    "early3d": "early3d", "3d": "early3d", "ps1": "early3d", "n64": "early3d", "saturn": "early3d",
    "64bit": "64bit", "dvd": "64bit", "ps2": "64bit", "gamecube": "64bit", "xbox": "64bit",
    "earlyhd": "earlyhd", "hd": "earlyhd", "ps3": "earlyhd", "xbox360": "earlyhd",
    "modern": "modern", "ps5": "modern", "current": "modern", "seriesx": "modern",
    "nextgen": "nextgen", "next": "nextgen", "future": "nextgen", "ps6": "nextgen",
}

_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "8bit": ("nes", "8-bit", "8bit", "famicom", "chiptune", "game boy", "pixel cart"),
    "16bit": ("snes", "genesis", "16-bit", "16bit", "mega drive", "mode-7", "mode 7"),
    "early3d": ("ps1", "n64", "saturn", "playstation 1", "low poly", "early 3d", "psx"),
    "64bit": ("ps2", "gamecube", "original xbox", "dreamcast"),
    "earlyhd": ("ps3", "xbox 360", "720p", "early hd"),
    "modern": ("ps5", "series x", "4k", "ray trac", "nanite"),
    "nextgen": ("ps6", "8k", "path trac", "next-gen", "nextgen"),
}

_NES = ("#000000", "#fcfcfc", "#f83800", "#0078f8", "#00b800", "#f8b800", "#3cbcfc", "#7c7c7c")
_SNES = ("#1a103c", "#f4e4c1", "#c43c3c", "#3c6e9a", "#3c8c4c", "#d4a44c", "#8c5cb4", "#2c2c44")


def get_generation(key: Optional[str]) -> Dict[str, Any]:
    if not key:
        return GENERATIONS[DEFAULT_GENERATION]
    k = str(key).strip().lower().replace("-", "").replace(" ", "").replace("/", "")
    return GENERATIONS.get(_ALIAS.get(k, k), GENERATIONS[DEFAULT_GENERATION])


def catalog() -> List[Dict[str, Any]]:
    return [{
        "key": e["key"], "label": e["label"], "order": e["order"],
        "platforms": e["platforms"], "tagline": e["tagline"],
        "storage_label": e["storage_label"], "color_label": e["color_label"],
        "poly_label": e["poly_label"], "resolution": e["resolution"],
        "viewport": list(e["viewport"]), "audio_format": e["audio_format"],
        "asset_types": e["asset_types"], "texture_res": e["texture_res"],
        "max_sprites": e["max_sprites"], "asset_capacity": e["asset_capacity"],
        "usual_max_assets": e["usual_max_assets"], "outshine_pct": e["outshine_pct"],
        "file_count_standard": e["file_count_standard"], "max_poly": e["max_poly"],
    } for e in sorted(GENERATIONS.values(), key=lambda x: x["order"])]


def palette(generation: str, n: int = 8) -> List[str]:
    spec = get_generation(generation)
    n = max(4, min(n, 16 if spec["order"] > 1 else 8))
    if spec["key"] == "8bit":
        return list(_NES[:n])
    if spec["key"] == "16bit":
        return list(_SNES[:n])
    rng = random.Random(int.from_bytes(hashlib.sha256(spec["key"].encode()).digest()[:8], "big"))
    out = []
    for _ in range(n):
        out.append("#%02x%02x%02x" % (rng.randint(16, 240), rng.randint(16, 240), rng.randint(16, 240)))
    return out


def hex_to_color(hx: str) -> Tuple[float, float, float]:
    h = hx.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def detect_generation(text: str) -> Tuple[str, Dict[str, int]]:
    blob = (text or "").lower()
    scores = {k: sum(1 for w in words if w in blob) for k, words in _KEYWORDS.items()}
    best = max(scores, key=lambda k: (scores[k], -GENERATIONS[k]["order"]))
    if scores[best] <= 0:
        return DEFAULT_GENERATION, scores
    return best, scores


def attach(pack: Dict[str, Any], generation: Optional[str] = None) -> Dict[str, Any]:
    spec = get_generation(generation or pack.get("hardware", {}).get("key"))
    pack["hardware"] = {
        "key": spec["key"],
        "label": spec["label"],
        "order": spec["order"],
        "platforms": list(spec["platforms"]),
        "tagline": spec["tagline"],
        "resolution": spec["resolution"],
        "viewport": list(spec["viewport"]),
        "colors_max": spec["colors_max"],
        "max_poly": spec["max_poly"],
        "audio_format": spec["audio_format"],
        "asset_types": list(spec["asset_types"]),
        "asset_capacity": spec["asset_capacity"],
        "file_count_standard": spec["file_count_standard"],
        "outshine_pct": spec["outshine_pct"],
        "storage_bytes": list(spec["storage_bytes"]),
        "storage_label": spec["storage_label"],
        "palette": palette(spec["key"]),
        "pixel_snap": spec["order"] <= 1,
        "sfx_format": {"8bit": "nsf", "16bit": "spc"}.get(spec["key"], "ogg"),
    }
    return pack


def list_generations() -> List[str]:
    return list(GEN_ORDER)
