"""Exact artist/procedural sprite parity across console, browser and Godot.

Proves that the same indexed pixel data was authored into every platform
source package and actual PNG files. This does NOT observe real pixels drawn
by Chromium, Godot, a console emulator or physical hardware.
"""
from __future__ import annotations

from hashlib import sha256
from base64 import b64decode
import json
from pathlib import Path

from skeleton.jeeves.game_console_assets import decode_tiles, decode_png

from .contracts import canonical_digest
from .studio_build_qualification import _regular

SCHEMA = "skeleton.game_builder.studio_cross_engine_pixel_parity.v1"
_MARKER = "const GAME = "


class StudioPixelParityError(ValueError):
    """One of the original source, palette, sprite or frame copies diverged."""


def _input(path: Path, max_size: int = 2_000_000) -> bytes:
    try:
        return _regular(path, max_size)
    except (OSError, ValueError) as exc:
        raise StudioPixelParityError("missing or unsafe generated pixel evidence") from exc


def _game_json(html: str) -> dict:
    if html.count(_MARKER) != 1:
        raise StudioPixelParityError("HTML5 original-game source has no canonical game payload")
    text = html.split(_MARKER, 1)[1]
    try:
        decoded, offset = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as exc:
        raise StudioPixelParityError("HTML5 pixel source is not canonical JSON") from exc
    if type(decoded) is not dict or not text[offset:].startswith(";"):
        raise StudioPixelParityError("HTML5 generated game JSON is not one source expression")
    return decoded


def inspect_cross_engine_pixels(project_root: str | Path) -> dict:
    """Verify exact 6×8×8 indexed pixels and all authored animation frames."""
    root = Path(project_root)
    if not root.is_dir() or root.is_symlink():
        raise StudioPixelParityError("real generated original source project required")
    source = root / "assets"
    engine = root / "engines"
    descriptors = json.loads(_input(source / "metadata/descriptors.json", 128_000))
    receipt = json.loads(_input(source / "metadata/manifest.json", 128_000))
    engine_release = json.loads(_input(engine / "release.json", 128_000))
    godot = json.loads(_input(engine / "godot/studio_art.json", 128_000))
    html_bytes = _input(engine / "index.html")
    game = _game_json(html_bytes.decode("utf-8"))
    if (descriptors.get("schema_version") != SCHEMA.replace(
            "studio_cross_engine_pixel_parity", "original_studio_art")
            or receipt.get("schema_version") != descriptors.get("schema_version")
            or type(receipt.get("pack_digest")) is not str
            or game.get("world_digest") != receipt.get("world_digest")
            or godot.get("world_digest") != receipt.get("world_digest")
            or godot.get("pack_digest") != receipt.get("pack_digest")
            or game.get("studio_art", {}).get("pack_digest") != receipt.get("pack_digest")
            or engine_release.get("studio_art_pack_digest") != receipt.get("pack_digest")):
        raise StudioPixelParityError("native/browser/Godot original studio source identity mismatch")
    if canonical_digest({k: v for k, v in receipt.items()
                         if k != "pack_digest"}) != receipt.get("pack_digest"):
        raise StudioPixelParityError("original artist artwork manifest was modified")
    files = receipt.get("files")
    if type(files) is not dict or len(files) > 32:
        raise StudioPixelParityError("original atlas file inventory invalid")
    for relative, identity in files.items():
        if (type(relative) is not str or relative.startswith("/")
                or ".." in Path(relative).parts or type(identity) is not dict):
            raise StudioPixelParityError("unsafe authored asset inventory")
        data = _input(source / relative)
        if (identity.get("sha256") != sha256(data).hexdigest()
                or identity.get("bytes") != len(data)):
            raise StudioPixelParityError("source PNG/animation/descriptor mutated")
    release_files = engine_release.get("files")
    if (type(release_files) is not dict
            or canonical_digest({k: v for k, v in engine_release.items()
                                 if k != "manifest_digest"}) != engine_release.get("manifest_digest")):
        raise StudioPixelParityError("engine source manifest corrupted")
    for key in ("index.html", "godot/studio_art.json"):
        data = html_bytes if key == "index.html" else _input(engine / key)
        if sha256(data).hexdigest() != release_files.get(key):
            raise StudioPixelParityError("browser or Godot original art file changed")
    native = _input(source / "tiles/runtime.bin", 2048)
    frames = _input(source / "tiles/hero_animation.bin", 2048)
    codec = descriptors.get("codec")
    try:
        tiles = decode_tiles(native, codec)
        animation = decode_tiles(frames, codec)
    except (ValueError, TypeError) as exc:
        raise StudioPixelParityError("platform native 2bpp/4bpp tile data invalid") from exc
    browser = game.get("studio_art", {})
    if (len(tiles) != 6 or not 1 <= len(animation) <= 4
            or [list(tile) for tile in tiles] != browser.get("tiles")
            or browser.get("tiles") != godot.get("tiles")
            or [list(frame) for frame in animation] != browser.get("frames")
            or browser.get("frames") != godot.get("frames")
            or descriptors.get("animation", {}).get("fps") != browser.get("fps")
            or browser.get("fps") != godot.get("fps")
            or sha256(native).hexdigest() != receipt.get("source_tile_digest")):
        raise StudioPixelParityError("original indexed sprite pixels or frames do not match")
    palette = descriptors.get("palette")
    hex_palette = ["#" + entry[:6] for entry in palette]
    if browser.get("palette") != hex_palette or godot.get("palette") != hex_palette:
        raise StudioPixelParityError("browser/Godot colors diverge from original palette")
    width, height, pixels = decode_png(_input(source / "sprites/atlas.png"))
    if (width, height) != (48, 8):
        raise StudioPixelParityError("original tile atlas geometry altered")
    rgba_palette = tuple(bytes.fromhex(c) for c in palette)
    for i, tile in enumerate(tiles):
        for y in range(8):
            for x in range(8):
                offset = (y * 48 + i * 8 + x) * 4
                if pixels[offset:offset + 4] != bytes(rgba_palette[tile[y * 8 + x]]):
                    raise StudioPixelParityError("rendered PNG pixel differs from console indexed tile")
    # Authored ambience, audio cues and PNG overlays must be the exact same
    # source bytes in playable HTML, standalone assets and Godot packages.
    original_audio = ("ambient", "collectible", "hazard")
    media = game.get("studio_media", {})
    if not isinstance(media, dict):
        raise StudioPixelParityError("browser media source is invalid")
    sounds = media.get("audio", {})
    layers = media.get("parallax", [])
    if not isinstance(sounds, dict) or not isinstance(layers, list):
        raise StudioPixelParityError("browser media payload is not typed")
    media_checked = 0
    for kind in original_audio:
        name = f"audio/{kind}.wav"
        present = name in files
        if present != (kind in sounds) or present != ("godot/" + name in release_files):
            raise StudioPixelParityError("original soundtrack differs across engines")
        if present:
            try:
                original = _input(source / name)
                embedded = b64decode(sounds[kind], validate=True)
                godot_pcm = _input(engine / "godot" / name)
            except (ValueError, TypeError, OSError) as exc:
                raise StudioPixelParityError("original browser audio cannot be decoded") from exc
            if (not original.startswith(b"RIFF") or original != embedded
                    or original != godot_pcm
                    or sha256(godot_pcm).hexdigest() != release_files["godot/" + name]):
                raise StudioPixelParityError("PCM sound bytes differ between console art, HTML and Godot")
            media_checked += 1
    expected_layers = sorted(
        name for name in files if name.startswith("parallax/") and name.endswith(".png")
    )
    if len(expected_layers) != len(layers) or len(layers) > 3:
        raise StudioPixelParityError("environment overlay count differs across engines")
    for name, encoded in zip(expected_layers, layers):
        if "godot/" + name not in release_files:
            raise StudioPixelParityError("Godot parallax source asset missing")
        try:
            expected_png = _input(source / name)
            embedded_png = b64decode(encoded, validate=True)
            godot_png = _input(engine / "godot" / name)
        except (ValueError, TypeError, OSError) as exc:
            raise StudioPixelParityError("environment PNG encoding was altered") from exc
        if (expected_png != embedded_png or expected_png != godot_png
                or sha256(godot_png).hexdigest() != release_files["godot/" + name]):
            raise StudioPixelParityError("original parallax pixels differ across runtime engines")
        media_checked += 1

    level_count = len(game.get("levels", []))
    if level_count < 1 or level_count > 8:
        raise StudioPixelParityError("original game level count unsupported")
    preview_info = []
    for index, level in enumerate(game["levels"]):
        png = _input(source / f"previews/level_{index:02d}.png")
        w, h, raw = decode_png(png)
        if (w, h) != (level.get("width", 0) * 8, level.get("height", 0) * 8):
            raise StudioPixelParityError("preview pixel dimensions differ from executable game")
        if len(raw) != w * h * 4:
            raise StudioPixelParityError("preview raster extent differs")
        preview_info.append(sha256(png).hexdigest())
    body = {
        "schema": SCHEMA, "project_id": receipt.get("project_id"),
        "target": receipt.get("target"), "world_digest": receipt.get("world_digest"),
        "studio_art_pack_digest": receipt["pack_digest"],
        "native_tile_bytes_sha256": sha256(native).hexdigest(),
        "browser_html_sha256": sha256(html_bytes).hexdigest(),
        "godot_art_sha256": sha256(_input(engine / "godot/studio_art.json")).hexdigest(),
        "sprite_atlas_sha256": sha256(_input(source / "sprites/atlas.png")).hexdigest(),
        "preview_digests": preview_info,
        "matching_semantic_tiles": len(tiles), "matching_animation_frames": len(animation),
        "matching_palette_entries": len(palette),
        "matching_original_audio_and_overlay_assets": media_checked,
        "runtime_graphical_pixels_observed": False,
        "release_certified": False,
    }
    return {**body, "receipt_digest": canonical_digest(body)}


__all__ = ["StudioPixelParityError", "inspect_cross_engine_pixels"]
