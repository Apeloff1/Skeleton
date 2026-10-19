"""Original deterministic stage media (PNG scene vistas and WAV ambience).

Only authored world data and Python standard library are used. Images and
audio are ORIGINAL procedural scaffolds, not upscaled licensed content or
professional assets. Reconstruct bytes identically during source verification.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import wave
import zlib
from typing import Any

SCHEMA = "skeleton.jeeves.director_generated_media.v1"
WIDTH, HEIGHT = 256, 144
SAMPLE_RATE = 16000
SAMPLES = 16000
MAX_MEDIA_BYTES = 24 * 1024 * 1024


def _png_chunk(name: bytes, raw: bytes) -> bytes:
    return (struct.pack(">I", len(raw)) + name + raw
            + struct.pack(">I", zlib.crc32(name + raw) & 0xFFFFFFFF))


def vista(scene: Any, world_digest: str) -> bytes:
    """A color-graded three-depth panorama with seeded skyline and light."""
    seed = hashlib.sha256((world_digest + ":" + scene.key).encode("ascii")).digest()
    sky = (19 + seed[0] // 7, 38 + seed[1] // 5, 65 + seed[2] // 5)
    weather = scene.weather.lower()
    if "sun" in weather or "clear" in weather:
        sky = (66 + seed[0] // 5, 107 + seed[1] // 4, 154 + seed[2] // 4)
    if "rain" in weather or "storm" in weather:
        sky = (25, 38, 59)
    if "snow" in weather:
        sky = (80, 101, 124)
    scanlines = bytearray()
    skyline = [41 + ((seed[x % 32] * 17 + (x // 8) * 41) % 35)
               for x in range(WIDTH // 8 + 1)]
    towers = [74 + ((seed[(x + 9) % 32] * 13 + x * 23) % 36)
              for x in range(WIDTH // 16 + 1)]
    for y in range(HEIGHT):
        scanlines.append(0)
        for x in range(WIDTH):
            glow = max(0, 26 - ((x - 195) ** 2 + (y - 29) ** 2) // 130)
            rgb = tuple(min(255, c + glow + y // 18) for c in sky)
            if y >= skyline[x // 8]:
                rgb = (19 + seed[11] // 17, 43 + seed[13] // 9, 60 + seed[17] // 8)
            if y >= towers[x // 16]:
                rgb = (24 + seed[22] // 11, 39 + seed[23] // 10, 45 + seed[25] // 8)
                if (x % 16 in (3, 4, 10)) and (y % 14 in (4, 5, 6)):
                    rgb = (217, 161 + seed[20] // 6, 81)
            if y > 117 + ((x // 11 + seed[7]) % 7):
                rgb = (14, 34, 34)
            if "rain" in weather and (x * 13 + y * 17 + seed[8]) % 71 == 0:
                rgb = tuple(min(255, c + 48) for c in rgb)
            scanlines.extend(rgb)
    body = b"\x89PNG\r\n\x1a\n"
    body += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
    body += _png_chunk(b"IDAT", zlib.compress(bytes(scanlines), 7))
    body += _png_chunk(b"IEND", b"")
    return body


def score(label: str) -> bytes:
    """A softly gated harmonically related sound loop, not a generated song."""
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    fundamental = 110.0 * (2 ** ((digest[0] % 12) / 12.0))
    interval = (3, 4, 5, 7)[digest[1] % 4]
    secondary = fundamental * (2 ** (interval / 12.0))
    frames = bytearray()
    for i in range(SAMPLES):
        t = i / SAMPLE_RATE
        phase = i / SAMPLES
        ramp = min(1.0, phase * 30.0, (1.0 - phase) * 30.0)
        modulation = 0.72 + 0.16 * math.sin(2 * math.pi * t * 2)
        value = (math.sin(2 * math.pi * fundamental * t) * 0.55
                 + math.sin(2 * math.pi * secondary * t) * 0.23
                 + math.sin(2 * math.pi * fundamental * 0.5 * t) * 0.15)
        frames.extend(struct.pack("<h", int(max(-1, min(1, value * ramp * modulation)) * 9000)))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(bytes(frames))
    return buffer.getvalue()


def generate(world: Any) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Pure bytes+manifest; binds scene IDs and soundtrack labels to verified assets."""
    assets: dict[str, bytes] = {}
    music: dict[str, str] = {}
    scenes: dict[str, dict[str, str]] = {}
    for scene in world.scenes:
        backdrop = "media/scene_" + scene.key + ".png"
        assets[backdrop] = vista(scene, world.digest)
        if scene.music not in music:
            key = hashlib.sha256(scene.music.encode("utf-8")).hexdigest()[:20]
            path = "media/score_" + key + ".wav"
            music[scene.music] = path
            assets[path] = score(scene.music)
        scenes[scene.key] = {
            "backdrop": "res://" + backdrop,
            "music": "res://" + music[scene.music],
        }
    total = sum(len(x) for x in assets.values())
    if total > MAX_MEDIA_BYTES:
        raise ValueError("original media generation exceeds bounded export capacity")
    catalog = {
        "schema": SCHEMA, "world_sha256": world.digest,
        "scenes": scenes,
        "procedural_media_only": True,
        "original_exported_audio_music_count": len(music),
        "original_exported_scene_image_count": len(scenes),
        "user_copyrighted_media_extracted": False,
        "professional_asset_quality_verified": False,
        "media_sha256": {
            path: hashlib.sha256(data).hexdigest()
            for path, data in sorted(assets.items())
        },
    }
    assets["media_catalog.json"] = (
        json.dumps(catalog, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    return assets, catalog
