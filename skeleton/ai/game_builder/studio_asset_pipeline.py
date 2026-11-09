"""Original console art production, pixel descriptors and actual preview rendering.

This module belongs to the existing game-builder engine. It reuses the
canonical console tile codec/PNG owner, and never invents a new renderer,
provider, device emulator, or game-release authority. Generated runtime
tile bytes are consumed by the GB/CGB/NES source emitters when opted in.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import pi, sin
from struct import pack as pack_integer
import wave
from hashlib import sha256
import json
from pathlib import Path

from skeleton.jeeves.game_console_assets import (
    TileCodec, decode_png, decode_tiles, encode_tiles, png_rgba,
)
from .contracts import canonical_digest
from .playable_world import PlayableWorld
from .studio_sprite_authoring import ArtistSpriteAtlas, palette_identity


SCHEMA = "skeleton.game_builder.original_studio_art.v1"
TILE_NAMES = ("floor", "wall", "collectible", "hazard", "goal", "hero")
SYMBOLS = {".": 0, "S": 0, "#": 1, "C": 2, "H": 3, "G": 4}
CODECS = {
    "nintendo_game_boy": TileCodec.GB_2BPP,
    "nintendo_game_boy_color": TileCodec.GB_2BPP,
    "nintendo_famicom": TileCodec.NES_2BPP,
    "sega_master_system": TileCodec.SMS_4BPP,
    "sega_game_gear": TileCodec.SMS_4BPP,
    "windows_modern": TileCodec.INDEXED_8BPP,
    "linux_desktop": TileCodec.INDEXED_8BPP,
    "macos_modern": TileCodec.INDEXED_8BPP,
    # These targets receive real portable asset previews and editable data;
    # their existing native source exporters do not yet consume these tiles.
    "commodore_64": TileCodec.INDEXED_8BPP,
    "dos_vga": TileCodec.INDEXED_8BPP,
    "atari_400_800": TileCodec.INDEXED_8BPP,
    "apple_ii": TileCodec.INDEXED_8BPP,
    "sinclair_zx_spectrum": TileCodec.INDEXED_8BPP,
    "msx1": TileCodec.INDEXED_8BPP,
    "colecovision": TileCodec.INDEXED_8BPP,
    "vectrex": TileCodec.INDEXED_8BPP,
}
NATIVE_EMBEDDED_TARGETS = frozenset({
    "nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom",
    "sega_master_system", "sega_game_gear",
})
STYLES = frozenset({"etched", "luminous", "organic", "arcade"})
PALETTES = {
    "forest": ("#142820", "#345D48", "#91B684", "#EFFAD3"),
    "ocean": ("#10273F", "#245C8B", "#4BBDD2", "#ECF9F5"),
    "desert": ("#3A2119", "#98623A", "#E8AF64", "#FFF0BE"),
    "space": ("#11152F", "#3F427F", "#9793DA", "#F5E9FF"),
    "arcade": ("#25152F", "#7E2B61", "#EB679E", "#FFEAD8"),
}


class StudioArtError(ValueError):
    """Invalid asset recipe, renderer output or source/render consistency."""


@dataclass(frozen=True, slots=True)
class ArtDirection:
    style: str = "luminous"
    contrast: str = "classic"
    animation_frames: int = 3
    seed: int = 0
    # These affect real generated pixels, not merely descriptor labels.
    outline: bool = True
    highlight: bool = True
    foliage_density: int = 2
    shadow_strength: int = 1
    parallax_layers: int = 1
    music_density: int = 2
    animation_fps: int = 4

    def __post_init__(self) -> None:
        if self.style not in STYLES:
            raise StudioArtError("unsupported original pixel-art style")
        if self.contrast not in {"classic", "high"}:
            raise StudioArtError("unknown contrast mode")
        if type(self.animation_frames) is not int or not 1 <= self.animation_frames <= 4:
            raise StudioArtError("animation must have 1..4 actual pixel frames")
        if type(self.seed) is not int or not 0 <= self.seed < 2**63:
            raise StudioArtError("art seed out of bounds")
        if type(self.outline) is not bool or type(self.highlight) is not bool:
            raise StudioArtError("art modifiers must be booleans")
        for name, low, high in (
            ("foliage_density", 0, 4), ("shadow_strength", 0, 3),
            ("parallax_layers", 0, 3), ("music_density", 0, 4),
            ("animation_fps", 1, 24),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise StudioArtError("invalid bounded original art control: " + name)


@dataclass(frozen=True, slots=True)
class StudioArtPack:
    world_digest: str
    target: str
    codec: TileCodec
    direction: ArtDirection
    runtime_tiles: tuple[tuple[int, ...], ...]
    files: tuple[tuple[str, bytes], ...]
    manifest: dict

    @property
    def digest(self) -> str:
        return self.manifest["pack_digest"]

    def verify(self) -> None:
        if len(self.runtime_tiles) != 6 or any(
            len(tile) != 64 or any(type(px) is not int or px not in (0, 1, 2, 3) for px in tile)
            for tile in self.runtime_tiles
        ):
            raise StudioArtError("native runtime tile inventory is malformed")
        if not self.files or len(self.files) > 24:
            raise StudioArtError("asset file budget exceeded")
        paths = [name for name, _ in self.files]
        if len(paths) != len(set(paths)) or any(
            not isinstance(name, str) or not name or Path(name).is_absolute()
            or any(part in ("", ".", "..") for part in Path(name).parts)
            or not name.startswith(("tiles/", "sprites/", "previews/", "metadata/", "audio/", "parallax/"))
            for name in paths
        ):
            raise StudioArtError("invalid or duplicate art file path")
        for name, data in self.files:
            if not isinstance(data, bytes) or not data or len(data) > 1024 * 1024:
                raise StudioArtError("invalid or oversized asset")
            record = self.manifest["files"].get(name)
            if record != {"bytes": len(data), "sha256": sha256(data).hexdigest()}:
                raise StudioArtError("art file manifest does not match actual bytes")
        expected = {k: v for k, v in self.manifest.items() if k != "pack_digest"}
        if canonical_digest(expected) != self.digest:
            raise StudioArtError("art content address is corrupted")
        data = dict(self.files)
        if decode_tiles(data["tiles/runtime.bin"], self.codec) != self.runtime_tiles:
            raise StudioArtError("console tile codec roundtrip failed")
        # Inspect actual rendered bytes, never trust a metadata-only image.
        for name, content in self.files:
            if name.endswith(".png"):
                width, height, pixels = decode_png(content)
                if width * height * 4 != len(pixels):
                    raise StudioArtError("PNG raster dimensions differ")


def _recipe(style: str, seed: int, name: str, x: int, y: int) -> int:
    """Original bounded 2bpp 8x8 art; semantic silhouettes remain distinct."""
    variant = (seed + sum(name.encode()) * 17) % 3
    dx, dy = abs(2 * x - 7), abs(2 * y - 7)
    ring = max(dx, dy)
    if name == "floor":
        return 1 if (x * 5 + y * 7 + variant) % (13 if style == "organic" else 19) == 0 else 0
    if name == "wall":
        mortar = y in (0, 4) or (x + (y // 4) * 3 + variant) % 7 == 0
        return 1 if mortar else (3 if ring >= 6 else 2)
    if name == "collectible":
        if dx + dy > 9:
            return 0
        return 3 if dx + dy < 4 else (1 if style == "etched" else 2)
    if name == "hazard":
        spike = x in (0, 7) or (y + x + variant) % 4 == 0
        return 3 if spike else (1 if dx + dy < 5 else 0)
    if name == "goal":
        return 3 if ring in (3, 5) else (2 if ring <= 2 else 0)
    if name == "hero":
        if ring >= 7:
            return 0
        if 2 <= x <= 5 and y in (2, 3):
            return 0 if x in (2, 5) else 3  # readable eyes
        return 3 if ring in (4, 5) else (2 if y < 4 else 1)
    raise StudioArtError("unknown sprite descriptor")


def _style_tile(name: str, direction: ArtDirection) -> tuple[int, ...]:
    values = []
    for y in range(8):
        for x in range(8):
            value = _recipe(direction.style, direction.seed, name, x, y)
            if direction.style == "arcade" and value == 1 and (x + y) % 3 == 0:
                value = 2
            elif direction.style == "organic" and value == 2 and (x * 3 + y * 5) % 7 == 0:
                value = 1
            if direction.outline and name in {"hero", "goal", "collectible"} and value == 2:
                if x in (1, 6) or y in (1, 6):
                    value = 1
            if not direction.highlight and value == 3 and name != "hero":
                value = 2
            if name == "floor" and direction.foliage_density > 0 and (
                x * 11 + y * 7 + direction.seed
            ) % (12 - direction.foliage_density * 2) == 0:
                value = 2
            if name == "wall" and direction.shadow_strength > 0 and (
                y >= 8 - direction.shadow_strength or x == 7
            ):
                value = max(0, value - 1)
            values.append(value)
    return tuple(values)


def _animate_hero(base: tuple[int, ...], frame: int) -> tuple[int, ...]:
    if frame == 0:
        return base
    result = list(base)
    if frame % 2:
        # Actual blinking pixels, not a metadata-only animation.
        for x in (3, 4):
            result[2 * 8 + x] = 2
    if frame >= 2:
        # Wing/arm motion visible on frame 2 and frame 3.
        for x, y in ((1, 4), (6, 4), (1, 5), (6, 5)):
            result[y * 8 + x] = 1 if frame == 2 else 0
    return tuple(result)


def _palette(theme: str, contrast: str) -> tuple[tuple[int, int, int, int], ...]:
    raw = PALETTES[theme]
    if contrast == "high":
        raw = (raw[0], "#3F3F3F", "#B8B8B8", "#FFFFFF")
    return tuple((*bytes.fromhex(c[1:]), 255) for c in raw)


def _rgba(tile: tuple[int, ...], palette: tuple[tuple[int, int, int, int], ...]) -> bytes:
    return b"".join(bytes(palette[index]) for index in tile)


def _preview(level, tiles, hero, palette) -> bytes:
    width, height = len(level.rows[0]) * 8, len(level.rows) * 8
    framebuffer = bytearray(width * height * 4)
    for ty, row in enumerate(level.rows):
        for tx, char in enumerate(row):
            if char not in SYMBOLS:
                raise StudioArtError("world contains an unknown tile marker")
            index = 5 if char == "S" else SYMBOLS[char]
            tile = hero if index == 5 else tiles[index]
            for y in range(8):
                for x in range(8):
                    color = bytes(palette[tile[y * 8 + x]])
                    at = ((ty * 8 + y) * width + tx * 8 + x) * 4
                    framebuffer[at:at + 4] = color
    return png_rgba(bytes(framebuffer), width, height)


def _environment_overlay(
    world: PlayableWorld, palette: tuple[tuple[int, int, int, int], ...],
    direction: ArtDirection, layer: int,
) -> bytes:
    """Original semi-transparent environmental imagery. Not native ROM VDP art."""
    width = world.intent.width * 8
    height = world.intent.height * 8
    data = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            line = (x * 17 + y * 11 + direction.seed + layer * 37) % 59
            foliage = (x * (3 + layer) + y * 7 + direction.seed) % 31
            if (direction.foliage_density and foliage < direction.foliage_density
                    and y > height // (3 + layer)):
                rgb = palette[2]
                alpha = 80 + layer * 30
            elif line == 0 and (y + layer * 4) % 13 < 3:
                rgb = palette[1]
                alpha = 46 + layer * 18
            else:
                continue
            offset = (y * width + x) * 4
            data[offset:offset + 4] = bytes((*rgb[:3], alpha))
    return png_rgba(bytes(data), width, height)


def _synthesized_wav(*, theme: str, seed: int, density: int, kind: str) -> bytes:
    """Emit deterministic original PCM music/cues, without copyrighted samples."""
    rate = 8000
    count = rate * (4 if kind == "ambient" else 1)
    roots = {"forest": 196, "ocean": 174, "desert": 220,
             "space": 146, "arcade": 261}
    notes = (0, 3, 5, 7, 10, 7, 5, 3)
    root = roots[theme]
    samples = bytearray()
    for n in range(count):
        step = (n // (rate // 4) + (seed % 8)) % len(notes)
        tone = root * (2 ** (notes[step] / 12))
        if kind == "collectible":
            tone = root * 2 + (n // 1100) * 140
        elif kind == "hazard":
            tone = max(95, root - 40 - (n // 800) * 9)
        second = tone * (1.5 if density > 1 else 1)
        envelope = min(1.0, n / 200.0, (count - n) / 240.0)
        amplitude = min(0.75, 0.13 + 0.09 * density)
        phase = 2 * pi * tone * n / rate
        overtone = sin(2 * pi * second * n / rate) if density > 1 else 0.0
        signal = sin(phase) * 0.8 + overtone * 0.2
        value = max(-32768, min(32767, int(32767 * amplitude * envelope * signal)))
        samples.extend(pack_integer("<h", value))
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples)
    return output.getvalue()


def render_studio_art(
    world: PlayableWorld, *, target: str, direction: ArtDirection, authorized: bool,
    artist_atlas: ArtistSpriteAtlas | None = None,
) -> StudioArtPack:
    """Compile real original 8x8 artwork, native tiles, and rendered frames."""
    if authorized is not True:
        raise PermissionError("original artwork generation requires scoped authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(direction, ArtDirection):
        raise StudioArtError("typed canonical world and art direction required")
    if target not in CODECS:
        raise StudioArtError("target has no qualified studio preview/codec adapter")
    palette = _palette(world.intent.theme, direction.contrast)
    if artist_atlas is not None:
        if not isinstance(artist_atlas, ArtistSpriteAtlas):
            raise StudioArtError("typed approved original pixel atlas required")
        if artist_atlas.palette_digest != palette_identity(palette):
            raise StudioArtError("artist atlas is not bound to destination game palette")
        tiles = artist_atlas.tiles
    else:
        tiles = tuple(_style_tile(name, direction) for name in TILE_NAMES)
    frames = tuple(_animate_hero(tiles[5], i) for i in range(direction.animation_frames))
    codec = CODECS[target]
    native = encode_tiles(tiles, codec)
    if decode_tiles(native, codec) != tiles:
        raise StudioArtError("native artwork did not survive actual planar codec")
    atlas_pixels = bytearray(8 * len(tiles) * 8 * 4)
    for index, tile in enumerate(tiles):
        for y in range(8):
            for x in range(8):
                at = (y * 8 * len(tiles) + index * 8 + x) * 4
                atlas_pixels[at:at + 4] = bytes(palette[tile[y * 8 + x]])
    files: dict[str, bytes] = {
        "tiles/runtime.bin": native,
        "tiles/hero_animation.bin": encode_tiles(frames, codec),
        "sprites/atlas.png": png_rgba(bytes(atlas_pixels), 8 * len(tiles), 8),
    }
    # Keep frame identity and a real pixel animation sequence for the preview
    # without falsely claiming that every native ROM drives these frames.
    for i, frame in enumerate(frames):
        files[f"sprites/hero_frame_{i:02d}.png"] = png_rgba(_rgba(frame, palette), 8, 8)
    for level in world.levels:
        files[f"previews/level_{level.index:02d}.png"] = _preview(level, tiles, frames[0], palette)
    if direction.parallax_layers:
        for layer in range(direction.parallax_layers):
            files[f"parallax/layer_{layer:02d}.png"] = _environment_overlay(
                world, palette, direction, layer,
            )
    if direction.music_density:
        for kind in ("ambient", "collectible", "hazard"):
            files[f"audio/{kind}.wav"] = _synthesized_wav(
                theme=world.intent.theme, seed=direction.seed,
                density=direction.music_density, kind=kind,
            )

    descriptors = {
        "schema_version": SCHEMA,
        "world_digest": world.digest,
        "target": target,
        "codec": codec.value,
        "tile_size": [8, 8],
        "palette": [c.hex() for c in (bytes(p) for p in palette)],
        "style": direction.style,
        "contrast": direction.contrast,
        "seed": direction.seed,
        "original_artist_atlas_used": artist_atlas is not None,
        "original_artist_source_sha256": (
            artist_atlas.source_sha256 if artist_atlas is not None else None
        ),
        "artist_quantization": (
            artist_atlas.quantization if artist_atlas is not None else None
        ),
        "artist_atlas_digest": (
            artist_atlas.digest if artist_atlas is not None else None
        ),
        "foliage_density": direction.foliage_density,
        "shadow_strength": direction.shadow_strength,
        "parallax_layers": direction.parallax_layers,
        "music_density": direction.music_density,
        "native_ambient_audio_integrated": False,
        "native_parallax_runtime_integrated": False,
        "outline": direction.outline,
        "highlight": direction.highlight,
        "animation_frames": direction.animation_frames,
        "sprites": [{
            "id": name, "tile_index": i, "bbox": [i * 8, 0, 8, 8],
            "role": "sprite" if name == "hero" else "background_tile",
            "collision": name in {"wall", "hazard"},
            "interactive": name in {"collectible", "goal", "hazard"},
            "rgba_preview": "sprites/atlas.png",
            "tile_digest": canonical_digest(list(tiles[i])),
        } for i, name in enumerate(TILE_NAMES)],
        "animation": {
            "sprite": "hero", "fps": direction.animation_fps,
            "frames": [f"sprites/hero_frame_{i:02d}.png" for i in range(len(frames))],
            "native_animation_driver_integrated": False,
        },
        "runtime_art_source_embedded": target in NATIVE_EMBEDDED_TARGETS,
        "hardware_color_registers_customized": False,
        "rights_independently_verified": False,
    }
    files["metadata/descriptors.json"] = (json.dumps(descriptors, sort_keys=True, indent=2) + "\n").encode()
    entries = {name: {"bytes": len(data), "sha256": sha256(data).hexdigest()}
               for name, data in sorted(files.items())}
    base = {
        "schema_version": SCHEMA,
        "world_digest": world.digest,
        "project_id": world.intent.project_id,
        "target": target,
        "codec": codec.value,
        "source_tile_digest": sha256(native).hexdigest(),
        "artist_source_digest": (
            artist_atlas.source_sha256 if artist_atlas is not None else None
        ),
        "artist_atlas_digest": artist_atlas.digest if artist_atlas is not None else None,

        "runtime_art_source_embedded": target in NATIVE_EMBEDDED_TARGETS,
        "native_binary_compiled": False,
        "native_emulator_verified": False,
        "screen_preview_rendered": True,
        "animation_frames_rendered": len(frames),
        "environment_overlay_layers_rendered": direction.parallax_layers,
        "original_pcm_cues_generated": 3 if direction.music_density else 0,
        "native_audio_driver_integrated": False,
        "native_parallax_driver_integrated": False,
        "native_animation_driver_integrated": False,
        "files": entries,
    }
    manifest = {**base, "pack_digest": canonical_digest(base)}
    pack = StudioArtPack(world.digest, target, codec, direction, tiles,
                         tuple(sorted(files.items())), manifest)
    pack.verify()
    return pack


def export_studio_art(pack: StudioArtPack, folder: str | Path, *, authorized: bool) -> dict:
    """Append an opt-in art payload only to a freshly created source directory.

    Existing source files are never overwritten. We preflight every path, use
    exclusive creates, and remove only our newly created files on failure.
    """
    if authorized is not True:
        raise PermissionError("art export requires explicit authorized output")
    if not isinstance(pack, StudioArtPack):
        raise StudioArtError("typed generated art pack required")
    pack.verify()
    root = Path(folder)
    if not root.is_dir() or root.is_symlink():
        raise StudioArtError("source project directory must exist and not be a symlink")
    base = root / "assets"
    if base.exists() or base.is_symlink():
        raise FileExistsError("studio asset directory already exists")
    base.mkdir()
    created: list[Path] = []
    directories: set[Path] = set()
    try:
        for relative, payload in (*pack.files, (
            "metadata/manifest.json",
            (json.dumps(pack.manifest, sort_keys=True, indent=2) + "\n").encode(),
        )):
            destination = base / relative
            if destination.parent not in directories:
                destination.parent.mkdir(parents=True, exist_ok=True)
                directories.add(destination.parent)
            with destination.open("xb") as stream:
                stream.write(payload)
            created.append(destination)
            if destination.read_bytes() != payload:
                raise StudioArtError("exported artwork bytes differ from generated bytes")
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
            directory.rmdir()
        base.rmdir()
        raise
    return {
        "pack_digest": pack.digest,
        "asset_files": len(created),
        "assets_directory": str(base),
        "source_tile_digest": pack.manifest["source_tile_digest"],
        "runtime_art_source_embedded": pack.target in NATIVE_EMBEDDED_TARGETS,
        "animation_frames_rendered": pack.direction.animation_frames,
        "native_binary_compiled": False,
        "emulator_verified": False,
    }
