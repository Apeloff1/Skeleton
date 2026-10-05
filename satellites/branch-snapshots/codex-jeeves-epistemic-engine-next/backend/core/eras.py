"""
╔════════════════════════════════════════════════════════════════════════╗
║  ERAS — the technical envelope every forge must respect.                ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Game-asset production was shaped by hardware. The chosen era sets the   ║
║  real limits the agents forge within: storage capacity, sprite/polygon   ║
║  budgets, colour palette, resolution and audio format/size. Sourced      ║
║  from the asset-metrics era table (8-Bit → Next-Gen).                    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import random
from typing import Any

_KB = 1024
_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024

# Ordered earliest → latest. Numbers come straight from the era spec table.
ERAS: dict[str, dict[str, Any]] = {
    "8bit": {
        "key": "8bit", "order": 0, "label": "8-Bit", "platforms": ["NES", "SMS"],
        "tagline": "Hand-drawn sprites, chiptune, cartridge-tight.",
        "storage_bytes": [8 * _KB, 1 * _MB],
        "storage_label": "8 KB – 1 MB",
        "max_sprites": 64, "sprite_dim": "8x8",
        "max_poly": 0, "poly_label": "2D · no polygons",
        "colors_max": 64, "color_label": "25–64 colors", "resolution": "256x240",
        "audio_format": "Chiptune synth", "audio_kb_range": [1, 5],
        "asset_kb_range": [1, 32],
        "asset_types": ["sprite_sheet", "icon", "thumbnail", "sfx", "palette_swatch"],
        "texture_res": "8x8–32x32 indexed",
    },
    "16bit": {
        "key": "16bit", "order": 1, "label": "16-Bit", "platforms": ["SNES", "Genesis"],
        "tagline": "Bigger sprites, compressed PCM, Mode-7 dreams.",
        "storage_bytes": [512 * _KB, 6 * _MB],
        "storage_label": "512 KB – 6 MB",
        "max_sprites": 128, "sprite_dim": "64x64",
        "max_poly": 0, "poly_label": "2D · no polygons",
        "colors_max": 512, "color_label": "256–512 colors", "resolution": "320x224",
        "audio_format": "Compressed 8-bit PCM", "audio_kb_range": [5, 64],
        "asset_kb_range": [8, 128],
        "asset_types": ["sprite_sheet", "icon", "thumbnail", "anim_clip", "sfx",
                        "vfx", "palette_swatch"],
        "texture_res": "up to 64x64 indexed",
    },
    "early3d": {
        "key": "early3d", "order": 2, "label": "Early 3D", "platforms": ["PS1", "N64", "Saturn"],
        "tagline": "Polygons arrive — low-res textures, MIDI & ADPCM.",
        "storage_bytes": [12 * _MB, 650 * _MB],
        "storage_label": "12 MB – 650 MB",
        "max_sprites": 0, "sprite_dim": "—",
        "max_poly": 3000, "poly_label": "300–3,000 polys / model",
        "colors_max": 65536, "color_label": "16-bit color", "resolution": "320x240–640x480",
        "audio_format": "Sequenced MIDI & 11–32kHz", "audio_kb_range": [16, 512],
        "asset_kb_range": [64, 4096],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "64x64–256x256",
    },
    "64bit": {
        "key": "64bit", "order": 3, "label": "64-Bit / DVD", "platforms": ["PS2", "Xbox", "GameCube"],
        "tagline": "DVD-scale worlds, true-color, Dolby Pro Logic.",
        "storage_bytes": [int(1.4 * _GB), int(4.7 * _GB)],
        "storage_label": "1.4 GB – 4.7 GB",
        "max_sprites": 0, "sprite_dim": "—",
        "max_poly": 10000, "poly_label": "3,000–10,000 polys / model",
        "colors_max": 16777216, "color_label": "24-bit color", "resolution": "480i–480p",
        "audio_format": "ADPCM Dolby Pro Logic", "audio_kb_range": [256, 8192],
        "asset_kb_range": [256, 32768],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "256x256–512x512",
    },
    "earlyhd": {
        "key": "earlyhd", "order": 4, "label": "Early HD", "platforms": ["PS3", "Xbox 360"],
        "tagline": "Normal maps, dynamic lighting, 5.1 surround.",
        "storage_bytes": [int(8.5 * _GB), 50 * _GB],
        "storage_label": "8.5 GB – 50 GB",
        "max_sprites": 0, "sprite_dim": "—",
        "max_poly": 50000, "poly_label": "10,000–50,000 polys / model",
        "colors_max": 16777216, "color_label": "true-color HD", "resolution": "720p–1080p",
        "audio_format": "Uncompressed 5.1 Surround", "audio_kb_range": [2048, 65536],
        "asset_kb_range": [1024, 262144],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "1024x1024–2048x2048",
    },
    "modern": {
        "key": "modern", "order": 5, "label": "Modern", "platforms": ["PS5", "Xbox Series", "PC"],
        "tagline": "4K textures, photogrammetry, real-time ray tracing.",
        "storage_bytes": [50 * _GB, 150 * _GB],
        "storage_label": "50 GB – 150 GB+",
        "max_sprites": 0, "sprite_dim": "—",
        "max_poly": 10000000, "poly_label": "Millions of polys (Nanite/Virtual)",
        "colors_max": 1073741824, "color_label": "10-bit HDR / 4K", "resolution": "2160p (4K)",
        "audio_format": "Spatial 3D audio (Atmos)", "audio_kb_range": [16384, 524288],
        "asset_kb_range": [8192, 2097152],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "4096x4096 (4K)",
    },
    "nextgen": {
        "key": "nextgen", "order": 6, "label": "Next-Gen", "platforms": ["PS6?", "Next Xbox", "PC"],
        "tagline": "8K textures, path tracing, object-based 3D audio.",
        "storage_bytes": [250 * _GB, 500 * _GB],
        "storage_label": "250 GB – 500 GB",
        "max_sprites": 0, "sprite_dim": "—",
        "max_poly": 100000000, "poly_label": "Billions virtualized (micropoly)",
        "colors_max": 1073741824, "color_label": "12-bit HDR / 8K", "resolution": "4320p (8K)",
        "audio_format": "Object-based 3D audio (path-traced)", "audio_kb_range": [65536, 1048576],
        "asset_kb_range": [16384, 8388608],
        "asset_types": ["sprite_sheet", "normal_map", "icon", "thumbnail", "sfx",
                        "vfx", "material", "lod_mesh", "anim_clip", "palette_swatch"],
        "texture_res": "8192x8192 (8K)",
    },
}

ERA_ORDER: list[str] = sorted(ERAS, key=lambda k: ERAS[k]["order"])
DEFAULT_ERA = "modern"

# ── "OUTSHINE EVERY ERA" asset capacity ───────────────────────────────────
# Our forge supports 40% ABOVE each era's historical max-usual asset count.
# Anchored by the user: NES (8-bit) ≥ 1,400 and Modern ≥ 1,400,000.
_USUAL_MAX_ASSETS: dict[str, int] = {
    "8bit": 1_000,
    "16bit": 4_000,
    "early3d": 15_000,
    "64bit": 60_000,
    "earlyhd": 250_000,
    "modern": 1_000_000,
    "nextgen": 4_000_000,
}
for _k, _spec in ERAS.items():
    _usual = _USUAL_MAX_ASSETS[_k]
    _spec["usual_max_assets"] = _usual
    _spec["asset_capacity"] = round(_usual * 1.4)  # +40% — we outshine the era
    _spec["outshine_pct"] = 40

# ── INDUSTRY-STANDARD SHIPPED FILE COUNT per era ───────────────────────────
# Representative unpacked total game-file counts for a flagship title of each
# era, grounded in real reverse-engineering / dev disclosures:
#   8-bit   Super Mario Bros (NES) ≈ 24 → genuine band ceiling ~200
#   16-bit  complex SNES carts (e.g. Chrono Trigger) ≈ 50–200 → ~1,200
#   early3D Final Fantasy VII (PS1) ≈ 3,500
#   64-bit  Metal Gear Solid 2 (PS2) ≈ 12,000
#   earlyHD Uncharted 3 (PS3) ≈ 45,000
#   modern  Cyberpunk 2077 / TLOU2 (PS4/PS5) ≈ 250,000
#   nextgen Elden Ring+ (PS5/XSX) ≈ 600,000
# The 100-phase build scales its produced file count to the chosen era so a
# Next-Gen build ships orders of magnitude more files than an 8-bit one.
_FILE_COUNT_STANDARD: dict[str, int] = {
    "8bit": 200,
    "16bit": 1_200,
    "early3d": 3_500,
    "64bit": 12_000,
    "earlyhd": 45_000,
    "modern": 250_000,
    "nextgen": 600_000,
}
for _k, _spec in ERAS.items():
    _spec["file_count_standard"] = _FILE_COUNT_STANDARD[_k]


def get_era(era_key: str | None) -> dict:
    """Resolve an era key (case/space tolerant) → spec; falls back to modern."""
    if not era_key:
        return ERAS[DEFAULT_ERA]
    k = str(era_key).strip().lower().replace("-", "").replace(" ", "").replace("/", "")
    alias = {"8bit": "8bit", "8": "8bit", "nes": "8bit",
             "16bit": "16bit", "16": "16bit", "snes": "16bit",
             "early3d": "early3d", "3d": "early3d", "ps1": "early3d",
             "64bit": "64bit", "dvd": "64bit", "ps2": "64bit",
             "earlyhd": "earlyhd", "hd": "earlyhd", "ps3": "earlyhd",
             "modern": "modern", "ps5": "modern", "current": "modern",
             "nextgen": "nextgen", "next": "nextgen", "future": "nextgen"}
    return ERAS.get(alias.get(k, k), ERAS[DEFAULT_ERA])


def humanize_bytes(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def catalog() -> list[dict]:
    """Lightweight era list for pickers/UI."""
    return [{
        "key": e["key"], "label": e["label"], "order": e["order"],
        "platforms": e["platforms"], "tagline": e["tagline"],
        "storage_label": e["storage_label"], "color_label": e["color_label"],
        "poly_label": e["poly_label"], "resolution": e["resolution"],
        "audio_format": e["audio_format"], "asset_types": e["asset_types"],
        "texture_res": e["texture_res"], "max_sprites": e["max_sprites"],
        "asset_capacity": e["asset_capacity"], "usual_max_assets": e["usual_max_assets"],
        "outshine_pct": e["outshine_pct"],
        "file_count_standard": e["file_count_standard"],
    } for e in sorted(ERAS.values(), key=lambda x: x["order"])]


def asset_spec(era_key: str | None, asset_type: str, rng: random.Random) -> dict:
    """Era-correct production spec for one asset: format, dims, size, poly."""
    era = get_era(era_key)
    lo, hi = era["asset_kb_range"]
    size_kb = rng.randint(lo, hi)
    is_audio = asset_type in ("sfx",)
    if is_audio:
        a_lo, a_hi = era["audio_kb_range"]
        size_kb = rng.randint(a_lo, a_hi)
    poly = 0
    if asset_type in ("lod_mesh", "material") and era["max_poly"] > 0:
        poly = rng.randint(max(1, era["max_poly"] // 10), era["max_poly"])
    fmt = {
        "sprite_sheet": "png", "normal_map": "png", "icon": "png", "thumbnail": "webp",
        "sfx": {"8bit": "nsf", "16bit": "spc"}.get(era["key"], "ogg"),
        "vfx": "json", "material": "json", "lod_mesh": "glb",
        "anim_clip": "json", "palette_swatch": "aco",
    }.get(asset_type, "bin")
    dims = era["texture_res"] if asset_type in (
        "sprite_sheet", "normal_map", "material", "icon", "thumbnail") else era["resolution"]
    return {
        "format": fmt, "dims": dims, "size_kb": size_kb, "poly": poly,
        "era": era["key"], "era_label": era["label"],
    }


def era_compliance(item: dict, era_key: str | None) -> dict:
    """Validate a forged item against its era's envelope. Used as a quality gate."""
    era = get_era(era_key)
    skin = item.get("skin") or {}
    checks = [
        ("palette_within_colors",
         len(skin.get("palette") or []) <= era["colors_max"]),
        ("poly_within_budget",
         int(skin.get("poly_budget", 0)) <= (era["max_poly"] if era["max_poly"] else 10**12)),
        ("era_tagged", (skin.get("era") == era["key"])),
    ]
    failed = [n for n, ok in checks if not ok]
    return {"era": era["key"], "passed": not failed, "failed": failed,
            "checks": [{"name": n, "passed": ok} for n, ok in checks]}
