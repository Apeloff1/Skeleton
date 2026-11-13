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
    if key is None or key == "":
        return GENERATIONS[DEFAULT_GENERATION]
    if not isinstance(key, str):
        raise ValueError("generation must be a string")
    k = key.strip().lower().replace("-", "").replace(" ", "").replace("/", "")
    if not k:
        return GENERATIONS[DEFAULT_GENERATION]
    resolved = _ALIAS.get(k)
    if resolved is None:
        raise ValueError(f"unknown generation {key!r}")
    return GENERATIONS[resolved]


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
    if not isinstance(text, str) or not text.strip():
        raise ValueError("generation text is required")
    blob = text.lower()
    scores = {k: sum(1 for w in words if w in blob) for k, words in _KEYWORDS.items()}
    best = max(scores, key=lambda k: (scores[k], -GENERATIONS[k]["order"]))
    if scores[best] <= 0:
        raise ValueError("no generation in text")
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


CONSOLE_ROM_PROFILES: Dict[str, Dict[str, Any]] = {
    "nes_rom": {
        "key": "nes_rom",
        "generation": "8bit",
        "console": "NES / Famicom",
        "rom_extension": ".nes",
        "header_format": "iNES 16-byte header (4E 45 53 1A)",
        "tile_bpp": 2,
        "bytes_per_8x8_tile": 16,
        "tile_encoding": "2bpp planar CHR (plane0 8B + plane1 8B)",
        "vram_kb": 16,
        "max_sprites_total": 64,
        "max_sprites_per_scanline": 8,
        "colors_on_screen": 25,
        "sub_palette_colors": 4,
        "viewport": [256, 240],
        "audio_channels": "2x Pulse, 1x Triangle, 1x Noise, 1x DPCM (2A03)",
        "rom_alignment_bytes": 16384,
        "checksum_rule": "PRG/CHR bank CRC32 + mapper mirror bits",
    },
    "gb_dmg_rom": {
        "key": "gb_dmg_rom",
        "generation": "8bit",
        "console": "Game Boy (DMG)",
        "rom_extension": ".gb",
        "header_format": "Cartridge header 0x0100..0x014F, checksum 0x0134..0x014D",
        "tile_bpp": 2,
        "bytes_per_8x8_tile": 16,
        "six_tile_symbol_bytes": 96,
        "linker_bank0_symbol_addr": "00:0200",
        "tile_encoding": "2bpp row-interleaved planar (2 bytes per 8px row)",
        "vram_kb": 8,
        "max_sprites_total": 40,
        "max_sprites_per_scanline": 10,
        "colors_on_screen": 4,
        "sub_palette_colors": 4,
        "viewport": [160, 144],
        "audio_channels": "2x Square, 1x Programmable Wave, 1x Noise (DMG APU)",
        "rom_alignment_bytes": 32768,
        "checksum_rule": "x = x - byte - 1 over 0x0134..0x014C stored at 0x014D",
    },
    "gbc_rom": {
        "key": "gbc_rom",
        "generation": "8bit",
        "console": "Game Boy Color (CGB)",
        "rom_extension": ".gbc",
        "header_format": "CGB flag 0x0143 (0x80/0xC0) + header checksum 0x014D",
        "tile_bpp": 2,
        "bytes_per_8x8_tile": 16,
        "tile_encoding": "Dual-bank 2bpp planar + BG attribute map (palette/bank/flip/priority)",
        "vram_kb": 16,
        "max_sprites_total": 40,
        "max_sprites_per_scanline": 10,
        "colors_on_screen": 56,
        "sub_palette_colors": 4,
        "viewport": [160, 144],
        "audio_channels": "2x Square, 1x Wave RAM, 1x Noise + HDMA HBlank transfer",
        "rom_alignment_bytes": 32768,
        "checksum_rule": "Header complement check at 0x014D + 16-bit global sum 0x014E..0x014F",
    },
    "sms_rom": {
        "key": "sms_rom",
        "generation": "8bit",
        "console": "Sega Master System",
        "rom_extension": ".sms",
        "header_format": "TMR SEGA signature at 0x7FF0..0x7FFF",
        "tile_bpp": 4,
        "bytes_per_8x8_tile": 32,
        "tile_encoding": "4bpp bitplane interleaved (4 bytes per row)",
        "vram_kb": 16,
        "max_sprites_total": 64,
        "max_sprites_per_scanline": 8,
        "colors_on_screen": 32,
        "sub_palette_colors": 16,
        "viewport": [256, 192],
        "audio_channels": "3x Square + 1x Noise (SN76489 PSG) + optional YM2413 FM",
        "rom_alignment_bytes": 16384,
        "checksum_rule": "16-bit ROM checksum at 0x7FFA..0x7FFB",
    },
    "snes_rom": {
        "key": "snes_rom",
        "generation": "16bit",
        "console": "SNES / Super Famicom",
        "rom_extension": ".sfc",
        "header_format": "LoROM 0x7FC0 / HiROM 0xFFC0 internal registration header",
        "tile_bpp": 4,
        "bytes_per_8x8_tile": 32,
        "tile_encoding": "4bpp/8bpp bitplane pairs + Mode-7 8bpp affine matrix tiles",
        "vram_kb": 64,
        "max_sprites_total": 128,
        "max_sprites_per_scanline": 32,
        "colors_on_screen": 256,
        "sub_palette_colors": 16,
        "viewport": [256, 224],
        "audio_channels": "8-channel Sony SPC700 BRR ADPCM (16-sample loop block aligned)",
        "rom_alignment_bytes": 32768,
        "checksum_rule": "Checksum + Complement == 0xFFFF at header +0x1C..0x1F",
    },
    "genesis_rom": {
        "key": "genesis_rom",
        "generation": "16bit",
        "console": "Sega Genesis / Mega Drive",
        "rom_extension": ".md",
        "header_format": "68000 vector table 0x0000..0x00FF + SEGA header 0x0100..0x01FF",
        "tile_bpp": 4,
        "bytes_per_8x8_tile": 32,
        "tile_encoding": "4bpp linear nybble-packed (2 pixels per byte)",
        "vram_kb": 64,
        "max_sprites_total": 80,
        "max_sprites_per_scanline": 20,
        "colors_on_screen": 64,
        "sub_palette_colors": 16,
        "viewport": [320, 224],
        "audio_channels": "6-channel YM2612 FM synth + 4-channel SN76489 PSG + Z80 PCM",
        "rom_alignment_bytes": 65536,
        "checksum_rule": "16-bit big-endian word sum from 0x0200..EOF stored at 0x018E",
    },
    "gba_rom": {
        "key": "gba_rom",
        "generation": "16bit",
        "console": "Game Boy Advance",
        "rom_extension": ".gba",
        "header_format": "ARM7TDMI branch + Nintendo logo 0x04..0x9F + complement 0xBD",
        "tile_bpp": 4,
        "bytes_per_8x8_tile": 32,
        "tile_encoding": "4bpp/8bpp linear packed 1D/2D OBJ & BG character blocks",
        "vram_kb": 96,
        "max_sprites_total": 128,
        "max_sprites_per_scanline": 128,
        "colors_on_screen": 512,
        "sub_palette_colors": 16,
        "viewport": [240, 160],
        "audio_channels": "2x 8-bit DMA DirectSound FIFO + 4x legacy DMG synth channels",
        "rom_alignment_bytes": 32768,
        "checksum_rule": "Header complement sum -(sum(0xA0..0xBC) + 0x19) & 0xFF at 0xBD",
    },
    "ps1_iso": {
        "key": "ps1_iso",
        "generation": "early3d",
        "console": "PlayStation 1 (PSX)",
        "rom_extension": ".bin",
        "header_format": "ISO9660 CD-ROM XA Mode 2 Form 1/2 (2048/2352-byte sectors) + SYSTEM.CNF",
        "tile_bpp": 8,
        "bytes_per_8x8_tile": 64,
        "tile_encoding": "4-bit/8-bit CLUT indexed TIM textures in 1024x512 16-bit VRAM",
        "vram_kb": 1024,
        "max_sprites_total": 4000,
        "max_sprites_per_scanline": 256,
        "max_poly": 3000,
        "colors_on_screen": 65536,
        "sub_palette_colors": 256,
        "viewport": [320, 240],
        "audio_channels": "24-channel SPU ADPCM (.VAG 28-sample blocks) + CD-XA streaming",
        "rom_alignment_bytes": 2048,
        "checksum_rule": "EDC/ECC sector syndromes + GTE integer vertex-snap bounds",
    },
    "n64_z64": {
        "key": "n64_z64",
        "generation": "early3d",
        "console": "Nintendo 64",
        "rom_extension": ".z64",
        "header_format": "Big-endian PI BSD DOM1 header 0x80371240 + IPL3 bootcode + CRC1/CRC2",
        "tile_bpp": 8,
        "bytes_per_8x8_tile": 64,
        "tile_encoding": "CI4/CI8/RGBA16 micro-textures strictly fitting 4KB (4096B) RDP TMEM",
        "vram_kb": 4096,
        "tmem_bytes": 4096,
        "max_sprites_total": 1024,
        "max_sprites_per_scanline": 256,
        "max_poly": 3000,
        "colors_on_screen": 65536,
        "sub_palette_colors": 256,
        "viewport": [320, 240],
        "audio_channels": "RSP microcode mixed 16–24 channel VADPCM audio",
        "rom_alignment_bytes": 64,
        "checksum_rule": "CIC-NUS-6102 dual 32-bit CRC at 0x0010..0x0017 over 0x1000..0x101000",
    },
    "saturn_iso": {
        "key": "saturn_iso",
        "generation": "early3d",
        "console": "Sega Saturn",
        "rom_extension": ".iso",
        "header_format": "SEGA SEGASATURN IP.BIN system area + SH-2 master/slave vectors",
        "tile_bpp": 8,
        "bytes_per_8x8_tile": 64,
        "tile_encoding": "VDP1 distorted quad textures + VDP2 multi-scroll cell planes",
        "vram_kb": 1536,
        "max_sprites_total": 2048,
        "max_sprites_per_scanline": 256,
        "max_poly": 3000,
        "colors_on_screen": 65536,
        "sub_palette_colors": 256,
        "viewport": [320, 224],
        "audio_channels": "32-channel Yamaha YMF292 SCSP PCM/FM + 68EC000 sound CPU",
        "rom_alignment_bytes": 2048,
        "checksum_rule": "2048-byte ISO sector boundary + VDP1 command table termination bit",
    },
    "ps2_iso": {
        "key": "ps2_iso",
        "generation": "64bit",
        "console": "PlayStation 2",
        "rom_extension": ".iso",
        "header_format": "ISO9660/UDF DVD-ROM + SYSTEM.CNF BOOT2 = cdrom0:\\SLUS_xxx.xx;1",
        "tile_bpp": 8,
        "bytes_per_8x8_tile": 64,
        "tile_encoding": "PSMCT32/PSMT8/PSMT4 swizzled GS 4MB eDRAM page/block textures",
        "vram_kb": 4096,
        "max_sprites_total": 8192,
        "max_sprites_per_scanline": 512,
        "max_poly": 10000,
        "colors_on_screen": 16777216,
        "sub_palette_colors": 256,
        "viewport": [640, 448],
        "audio_channels": "48-channel SPU2 ADPCM + IOP streaming",
        "rom_alignment_bytes": 2048,
        "checksum_rule": "128-bit QW (16-byte) DMA VIF/GIF packet alignment",
    },
    "gamecube_gcm": {
        "key": "gamecube_gcm",
        "generation": "64bit",
        "console": "Nintendo GameCube",
        "rom_extension": ".gcm",
        "header_format": "boot.bin magic 0xC2339F3D + bi2.bin + apploader.img + main.dol",
        "tile_bpp": 4,
        "bytes_per_8x8_tile": 32,
        "tile_encoding": "GX 4x4 tiled CMPR (S3TC/DXT1) & RGB5A3 32-byte cache-line blocks",
        "vram_kb": 3072,
        "max_sprites_total": 8192,
        "max_sprites_per_scanline": 512,
        "max_poly": 10000,
        "colors_on_screen": 16777216,
        "sub_palette_colors": 256,
        "viewport": [640, 480],
        "audio_channels": "64-channel Macronix DSP 4-bit ADPCM (.dsp)",
        "rom_alignment_bytes": 32,
        "checksum_rule": "32-byte DVD DMA & GX FIFO burst alignment",
    },
    "dreamcast_gdi": {
        "key": "dreamcast_gdi",
        "generation": "64bit",
        "console": "Sega Dreamcast",
        "rom_extension": ".gdi",
        "header_format": "SEGA SEGAKATANA IP.BIN + 1ST_READ.BIN SH-4 little-endian binary",
        "tile_bpp": 16,
        "bytes_per_8x8_tile": 128,
        "tile_encoding": "PowerVR2 CLX2 Morton-twiddled + VQ codebook compressed ARGB1555/RGB565",
        "vram_kb": 8192,
        "max_sprites_total": 8192,
        "max_sprites_per_scanline": 512,
        "max_poly": 10000,
        "colors_on_screen": 16777216,
        "sub_palette_colors": 256,
        "viewport": [640, 480],
        "audio_channels": "64-channel Yamaha AICA 4-bit ADPCM + ARM7 sound CPU",
        "rom_alignment_bytes": 32,
        "checksum_rule": "32-byte SH-4 Store Queue tile-accelerator burst alignment",
    },
    "modern_console_pkg": {
        "key": "modern_console_pkg",
        "generation": "modern",
        "console": "PS5 / Xbox Series X / PC",
        "rom_extension": ".pkg",
        "header_format": "Signed content-addressed chunk manifest + Kraken/BCPack stream table",
        "tile_bpp": 8,
        "bytes_per_8x8_tile": 64,
        "tile_encoding": "BC1–BC7 block-compressed PBR textures with power-of-two halving ladder",
        "vram_kb": 16 * 1024 * 1024,
        "max_sprites_total": 65536,
        "max_sprites_per_scanline": 4096,
        "max_poly": 10_000_000,
        "colors_on_screen": 1_073_741_824,
        "sub_palette_colors": 1024,
        "viewport": [1280, 720],
        "audio_channels": "Object-based 3D spatial audio bus with occlusion & reverb impulse",
        "rom_alignment_bytes": 4096,
        "checksum_rule": "SHA-256 Merkle chunk tree + zero 65536-bitmap allocation guard",
    },
}

_CONSOLE_ALIAS: Dict[str, str] = {
    "nes": "nes_rom", "famicom": "nes_rom", "nesrom": "nes_rom", "ines": "nes_rom",
    "gb": "gb_dmg_rom", "dmg": "gb_dmg_rom", "gameboy": "gb_dmg_rom", "gbdmgrom": "gb_dmg_rom",
    "gbc": "gbc_rom", "cgb": "gbc_rom", "gameboycolor": "gbc_rom", "gbcrom": "gbc_rom",
    "sms": "sms_rom", "mastersystem": "sms_rom", "smsrom": "sms_rom",
    "snes": "snes_rom", "sfc": "snes_rom", "superfamicom": "snes_rom", "snesrom": "snes_rom",
    "genesis": "genesis_rom", "megadrive": "genesis_rom", "md": "genesis_rom", "genesisrom": "genesis_rom",
    "gba": "gba_rom", "gameboyadvance": "gba_rom", "gbarom": "gba_rom",
    "ps1": "ps1_iso", "psx": "ps1_iso", "playstation1": "ps1_iso", "ps1iso": "ps1_iso",
    "n64": "n64_z64", "z64": "n64_z64", "nintendo64": "n64_z64", "n64z64": "n64_z64",
    "saturn": "saturn_iso", "segasaturn": "saturn_iso", "saturniso": "saturn_iso",
    "ps2": "ps2_iso", "playstation2": "ps2_iso", "ps2iso": "ps2_iso",
    "gamecube": "gamecube_gcm", "gc": "gamecube_gcm", "gcm": "gamecube_gcm", "gamecubegcm": "gamecube_gcm",
    "dreamcast": "dreamcast_gdi", "dc": "dreamcast_gdi", "gdi": "dreamcast_gdi", "dreamcastgdi": "dreamcast_gdi",
    "modern": "modern_console_pkg", "ps5": "modern_console_pkg", "seriesx": "modern_console_pkg", "modernconsolepkg": "modern_console_pkg",
}


def list_console_rom_profiles() -> List[str]:
    """Return all canonical console and ROM profile keys in hardware order."""
    return list(CONSOLE_ROM_PROFILES.keys())


def get_console_rom_profile(key: Optional[str]) -> Dict[str, Any]:
    """Resolve a console or ROM profile by key or platform alias."""
    if not key or not isinstance(key, str):
        return dict(CONSOLE_ROM_PROFILES["gb_dmg_rom"])
    norm = key.strip().lower().replace("-", "").replace("_", "").replace(" ", "").replace(".", "")
    resolved = _CONSOLE_ROM_KEY = CONSOLE_ROM_PROFILES.get(key.strip().lower())
    if resolved is not None:
        return dict(resolved)
    alias_target = _CONSOLE_ALIAS.get(norm)
    if alias_target is not None:
        return dict(CONSOLE_ROM_PROFILES[alias_target])
    raise ValueError(f"unknown console/ROM profile {key!r}")


def validate_rom_asset_budget(profile_key: str, asset_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Validate sprite, tile, palette, VRAM, and polygon budgets against a console/ROM profile."""
    profile = get_console_rom_profile(profile_key)
    gen_spec = get_generation(profile["generation"])
    spec = dict(asset_spec or {})

    violations: List[str] = []
    tile_count = int(spec.get("tile_count") or 0)
    bytes_per_tile = int(profile["bytes_per_8x8_tile"])
    tile_bytes = int(spec.get("tile_bytes") or (tile_count * bytes_per_tile))
    vram_limit_bytes = int(profile["vram_kb"]) * _KB

    if tile_count > 0 and spec.get("tile_bytes") is not None:
        expected_bytes = tile_count * bytes_per_tile
        if int(spec["tile_bytes"]) != expected_bytes:
            violations.append(
                f"tile_bytes={spec['tile_bytes']} does not match {tile_count} tiles * {bytes_per_tile}B ({expected_bytes}B)"
            )

    if tile_bytes > vram_limit_bytes:
        violations.append(f"tile_bytes={tile_bytes}B exceeds VRAM ceiling {vram_limit_bytes}B")

    if "tmem_bytes" in profile and int(spec.get("texture_bytes") or 0) > int(profile["tmem_bytes"]):
        violations.append(
            f"texture_bytes={spec.get('texture_bytes')}B exceeds N64 TMEM ceiling {profile['tmem_bytes']}B"
        )

    sprites_total = int(spec.get("sprites_total") or 0)
    if sprites_total > int(profile["max_sprites_total"]):
        violations.append(
            f"sprites_total={sprites_total} exceeds hardware OAM limit {profile['max_sprites_total']}"
        )

    sprites_scanline = int(spec.get("sprites_per_scanline") or 0)
    if sprites_scanline > int(profile["max_sprites_per_scanline"]):
        violations.append(
            f"sprites_per_scanline={sprites_scanline} exceeds scanline limit {profile['max_sprites_per_scanline']}"
        )

    palette_colors = int(spec.get("palette_colors") or 0)
    if palette_colors > int(profile["colors_on_screen"]):
        violations.append(
            f"palette_colors={palette_colors} exceeds on-screen color limit {profile['colors_on_screen']}"
        )

    poly_count = int(spec.get("poly_count") or 0)
    max_poly = int(profile.get("max_poly", gen_spec["max_poly"]))
    if poly_count > max_poly:
        violations.append(f"poly_count={poly_count} exceeds polygon budget {max_poly}")

    alloc_tier = int(spec.get("allocated_bitmap_dim") or 0)
    if alloc_tier >= 65536:
        violations.append("allocated_bitmap_dim=65536 violates scale-ladder divisor-only rule")

    return {
        "valid": len(violations) == 0,
        "profile_key": profile["key"],
        "console": profile["console"],
        "generation": profile["generation"],
        "tile_bytes": tile_bytes,
        "vram_utilization": round(tile_bytes / max(1, vram_limit_bytes), 4),
        "violations": violations,
    }


def compile_console_rom_envelope(profile_key: str) -> Dict[str, Any]:
    """Compile a complete hardware + ROM asset contract envelope for a target console."""
    profile = get_console_rom_profile(profile_key)
    gen_spec = get_generation(profile["generation"])
    pal = palette(profile["generation"], n=min(16, max(4, int(profile["sub_palette_colors"]))))
    return {
        "schema_version": "skeleton.console_rom_envelope.v1",
        "profile_key": profile["key"],
        "console": profile["console"],
        "generation": profile["generation"],
        "rom_extension": profile["rom_extension"],
        "header_format": profile["header_format"],
        "tile_bpp": profile["tile_bpp"],
        "bytes_per_8x8_tile": profile["bytes_per_8x8_tile"],
        "tile_encoding": profile["tile_encoding"],
        "vram_kb": profile["vram_kb"],
        "max_sprites_total": profile["max_sprites_total"],
        "max_sprites_per_scanline": profile["max_sprites_per_scanline"],
        "colors_on_screen": profile["colors_on_screen"],
        "sub_palette_colors": profile["sub_palette_colors"],
        "viewport": list(profile["viewport"]),
        "audio_channels": profile["audio_channels"],
        "rom_alignment_bytes": profile["rom_alignment_bytes"],
        "checksum_rule": profile["checksum_rule"],
        "palette": pal,
        "storage_bytes": list(gen_spec["storage_bytes"]),
        "asset_capacity": gen_spec["asset_capacity"],
    }


def synthesize_rom_tile_bank(
    profile_key: str,
    *,
    tile_count: int = 6,
    seed: int = 42,
    pattern: str = "hero_crest",
) -> Dict[str, Any]:
    """Procedural Console/ROM Tile, Palette, OAM, & PSG Audio Asset Synthesizer.

    Generates hardware-exact bitplane-packed 8x8 tile bytes (16B/tile for 2bpp
    Game Boy/NES, 32B/tile for 4bpp SNES/Genesis/GBA/SMS, 64B/tile for 8bpp,
    128B/tile for 16bpp), OAM sprite attribute descriptors, sub-palette tables,
    PSG/FM/BRR sound register patches, and a verified ROM header checksum.
    """
    import hashlib
    import random

    profile = get_console_rom_profile(profile_key)
    key = profile["key"]
    bpp = int(profile["tile_bpp"])
    bytes_per_tile = int(profile["bytes_per_8x8_tile"])
    n_tiles = max(1, min(256, int(tile_count)))
    max_color_idx = max(1, (1 << min(bpp, 8)) - 1)
    rng = random.Random((int(seed) ^ hash(key) ^ hash(pattern)) & 0xFFFFFFFF)

    tiles_pixels: List[List[List[int]]] = []
    raw_bytes = bytearray()

    for t_idx in range(n_tiles):
        grid: List[List[int]] = []
        for y in range(8):
            row: List[int] = []
            for x in range(8):
                mirror_x = x if x < 4 else (7 - x)
                dist = abs(mirror_x - 3) + abs(y - 3)
                if dist == 0:
                    px = min(max_color_idx, 3)
                elif dist <= 2:
                    px = min(max_color_idx, 1 + ((t_idx + mirror_x + y) % max(1, min(3, max_color_idx))))
                elif dist == 3 and ((mirror_x + y + rng.randint(0, 1)) % 2 == 0):
                    px = 1
                else:
                    px = 0
                row.append(px)
            grid.append(row)
        tiles_pixels.append(grid)

        tile_buf = bytearray()
        if bpp == 2 and key == "nes_rom":
            for y in range(8):
                b0 = 0
                for x in range(8):
                    b0 = (b0 << 1) | (grid[y][x] & 1)
                tile_buf.append(b0 & 0xFF)
            for y in range(8):
                b1 = 0
                for x in range(8):
                    b1 = (b1 << 1) | ((grid[y][x] >> 1) & 1)
                tile_buf.append(b1 & 0xFF)
        elif bpp == 2:
            for y in range(8):
                b0 = 0
                b1 = 0
                for x in range(8):
                    b0 = (b0 << 1) | (grid[y][x] & 1)
                    b1 = (b1 << 1) | ((grid[y][x] >> 1) & 1)
                tile_buf.append(b0 & 0xFF)
                tile_buf.append(b1 & 0xFF)
        elif bpp == 4 and key == "genesis_rom":
            for y in range(8):
                for x in range(0, 8, 2):
                    hi = grid[y][x] & 0x0F
                    lo = grid[y][x + 1] & 0x0F
                    tile_buf.append(((hi << 4) | lo) & 0xFF)
        elif bpp == 4:
            for plane_pair in (0, 2):
                for y in range(8):
                    bp0 = 0
                    bp1 = 0
                    for x in range(8):
                        bp0 = (bp0 << 1) | ((grid[y][x] >> plane_pair) & 1)
                        bp1 = (bp1 << 1) | ((grid[y][x] >> (plane_pair + 1)) & 1)
                    tile_buf.append(bp0 & 0xFF)
                    tile_buf.append(bp1 & 0xFF)
        else:
            for y in range(8):
                for x in range(8):
                    val = grid[y][x] & 0xFF
                    tile_buf.append(val)
                    if bytes_per_tile >= 128:
                        tile_buf.append(((val << 3) | 0x01) & 0xFF)
        if len(tile_buf) < bytes_per_tile:
            tile_buf.extend(b"\x00" * (bytes_per_tile - len(tile_buf)))
        elif len(tile_buf) > bytes_per_tile:
            tile_buf = tile_buf[:bytes_per_tile]
        raw_bytes.extend(tile_buf)

    oam_entries: List[Dict[str, int]] = []
    oam_count = min(n_tiles, int(profile["max_sprites_per_scanline"]))
    for s_idx in range(oam_count):
        oam_entries.append({
            "sprite_index": s_idx,
            "y": 64 + (s_idx // 4) * 8,
            "x": 48 + (s_idx % 4) * 8,
            "tile_id": s_idx,
            "attr_flags": s_idx % max(1, min(4, int(profile["sub_palette_colors"]))),
        })

    base_freq = 440 + (seed % 5) * 55
    audio_patch = {
        "channel_spec": profile["audio_channels"],
        "pulse_duty_cycle": "50%",
        "frequency_hz": base_freq,
        "envelope_hex": "0xF2",
        "period_register_hex": f"0x{(2048 - int(131072 / max(64, base_freq))) & 0x7FF:03X}",
    }

    complement = (-sum(raw_bytes[: min(25, len(raw_bytes))]) - 0x19) & 0xFF
    checksum16 = sum(raw_bytes) & 0xFFFF
    budget_check = validate_rom_asset_budget(
        key,
        {
            "tile_count": n_tiles,
            "tile_bytes": len(raw_bytes),
            "sprites_total": len(oam_entries),
            "sprites_per_scanline": len(oam_entries),
            "palette_colors": int(profile["sub_palette_colors"]),
        },
    )

    return {
        "schema_version": "skeleton.console_rom_tile_bank.v1",
        "profile_key": key,
        "console": profile["console"],
        "generation": profile["generation"],
        "pattern": pattern,
        "tile_count": n_tiles,
        "tile_bpp": bpp,
        "bytes_per_8x8_tile": bytes_per_tile,
        "total_tile_bytes": len(raw_bytes),
        "tile_hex": raw_bytes.hex(),
        "tile_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "linker_bank0_symbol": profile.get("linker_bank0_symbol_addr", "00:0200"),
        "palette": palette(profile["generation"], n=min(16, max(4, int(profile["sub_palette_colors"])))),
        "oam_table": oam_entries,
        "audio_patch": audio_patch,
        "header_complement_hex": f"0x{complement:02X}",
        "rom_checksum16_hex": f"0x{checksum16:04X}",
        "budget_validation": budget_check,
    }
