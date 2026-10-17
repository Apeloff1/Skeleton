"""Independent consistency audit of original console source, animation and PSG.

Runs on *every* completed GB/CGB/NES campaign target, before compiler/ROM
admission. Compares the actual authored tile assets, canonical browser world,
source manifest and exact emitted assembly data. This is source-level evidence,
not proof that an emulator rendered a sprite or emitted sound.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from skeleton.jeeves.game_console_assets import decode_tiles

from .contracts import canonical_digest
from .game_boy_native_export import _hero_frame_bytes
from .nes_native_export import _hero_frame_chr
from .studio_native_psg import compose_native_psg, console_psg_registers
from .studio_pixel_parity import _game_json, inspect_cross_engine_pixels
from .studio_runtime_qualification import _inputs

SCHEMA = "skeleton.game_builder.native_source_media_parity.v1"
_CONSOLES = frozenset({
    "nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom",
})


class NativeMediaSourceError(ValueError):
    """Published console assembler data differs from actual original art."""


def _bytes(file: Path, *, limit: int) -> bytes:
    if file.is_symlink() or not file.is_file():
        raise NativeMediaSourceError("original media source must be a regular file")
    size = file.stat().st_size
    if size < 1 or size > limit:
        raise NativeMediaSourceError("original source exceeds bounded media budget")
    return file.read_bytes()


def _object(file: Path, *, limit: int = 128_000) -> dict:
    try:
        value = json.loads(_bytes(file, limit=limit))
    except (UnicodeError, ValueError) as exc:
        raise NativeMediaSourceError("unparseable original source metadata") from exc
    if type(value) is not dict:
        raise NativeMediaSourceError("original source metadata must be a JSON object")
    return value


def _exact_region(source: str, begin: str, end: str, body: str) -> None:
    if (source.count(begin) != 1 or source.count(end) != 1
            or source.split(begin, 1)[1].split(end, 1)[0].strip() != body.strip()):
        raise NativeMediaSourceError("console source region diverges from authored media")


def inspect_native_source_media(project: str | Path, *, target: str) -> dict:
    if target not in _CONSOLES:
        raise NativeMediaSourceError("no console-native sprite and sound adapter for target")
    root = Path(project)
    if root.is_symlink() or not root.is_dir():
        raise NativeMediaSourceError("real original game source target required")

    try:
        parity = inspect_cross_engine_pixels(root)
        art = _object(root / "assets/metadata/descriptors.json")
        source_manifest = _object(root / "manifest.json")
        file_name = "main.s" if target == "nintendo_famicom" else "main.asm"
        source_bytes = _bytes(root / file_name, limit=512_000)
        source = source_bytes.decode("utf-8")
        _, _, world = _inputs(root / "engines")
        game = _game_json(_bytes(root / "engines/index.html", limit=2_000_000).decode("utf-8"))
        original = _bytes(root / "assets/tiles/runtime.bin", limit=512)
        animated = _bytes(root / "assets/tiles/hero_animation.bin", limit=128)
        tiles = decode_tiles(original, art["codec"])
        frames = decode_tiles(animated, art["codec"])
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        raise NativeMediaSourceError("original source art or game bundle cannot be checked") from exc
    if (art.get("target") != target
            or art.get("world_digest") != world
            or game.get("world_digest") != world
            or type(game.get("intent")) is not dict
            or game["intent"].get("theme") is None
            or source_manifest.get("world_digest") != world
            or len(tiles) != 6 or not 1 <= len(frames) <= 4
            or frames[0] != tiles[5]
            or any(len(frame) != 64 for frame in frames)):
        raise NativeMediaSourceError("actual original hero frames or canonical world diverged")

    fps = art.get("animation", {}).get("fps")
    if type(fps) is not int or fps < 1 or fps > 60:
        raise NativeMediaSourceError("original animation speed is out of console bounds")
    delay = max(2, min(60, round(60 / fps)))
    expected_frame_digest = canonical_digest([list(frame) for frame in frames])
    if (source_manifest.get("native_hero_animation_frames") != len(frames)
            or source_manifest.get("native_hero_animation_frame_delay") != delay
            or source_manifest.get("native_hero_animation_compiled") != (len(frames) > 1)
            or source_manifest.get("native_hero_animation_digest") != expected_frame_digest):
        raise NativeMediaSourceError("native source frame manifest differs from actual indexed pixels")

    nes = target == "nintendo_famicom"
    if nes:
        expected_frames = (_hero_frame_chr(frames[1:]) if len(frames) > 1
                           else "; single original player sprite")
        _exact_region(source, "AnimationTiles:\n", "\nAnimationTilesEnd:", expected_frames)
        if (f"ANIM_COUNT = {len(frames)}\n" not in source
                or f"ANIM_DELAY = {delay}\n" not in source):
            raise NativeMediaSourceError("NES native sprite driver has wrong frame or tick count")
    else:
        expected_frames = (_hero_frame_bytes(frames[1:]) if len(frames) > 1
                           else "    ; single original hero frame")
        _exact_region(source, "AnimationTiles:\n", "\nAnimationTilesEnd:", expected_frames)
        if (f"DEF ANIM_COUNT EQU {len(frames)}\n" not in source
                or f"DEF ANIM_DELAY EQU {delay}\n" not in source):
            raise NativeMediaSourceError("GB/CGB native sprite driver has wrong frame or tick count")

    theme = game["intent"]["theme"]
    density = art.get("music_density")
    seed = art.get("seed")
    try:
        score = compose_native_psg(theme, seed, density)
        programmed = console_psg_registers(score, target)
    except (TypeError, ValueError) as exc:
        raise NativeMediaSourceError("original game PSG score cannot be generated") from exc
    if (source_manifest.get("native_psg_score_digest") != score.digest
            or source_manifest.get("original_native_psg_integrated") != (density > 0)
            or source_manifest.get("native_psg_hardware_audio_played") is not False
            or source_manifest.get("native_psg_not_pcm_identity") is not True):
        raise NativeMediaSourceError("native game source's original music digest is inconsistent")

    low = programmed["notes_low"]
    high = programmed["notes_high"]
    low_line = (
        ".byte " if nes else "    db "
    ) + ", ".join(f"${number:02X}" for number in low)
    high_line = (
        ".byte " if nes else "    db "
    ) + ", ".join(f"${number:02X}" for number in high)
    _exact_region(source, "OriginalMusicLow:\n", "\nOriginalMusicHigh:", low_line)
    if (source.count("OriginalMusicHigh:\n") != 1
            or source.split("OriginalMusicHigh:\n", 1)[1].splitlines()[0].strip()
            != high_line.strip()):
        raise NativeMediaSourceError("native music high-register table changed")
    if nes:
        if (f"AUDIO_ENABLED = {int(density > 0)}\n" not in source
                or f"MUSIC_FRAME_DELAY = {programmed['frames_per_note']}\n" not in source):
            raise NativeMediaSourceError("NES APU enable/timing mismatches original score")
    elif (f"DEF AUDIO_ENABLED EQU {int(density > 0)}\n" not in source
          or f"DEF MUSIC_FRAME_DELAY EQU {programmed['frames_per_note']}\n" not in source):
        raise NativeMediaSourceError("GB APU enable/timing mismatches original score")
    sections = ("SoundPickup", "SoundHazard", "SoundGoal")
    after = ("SoundHazard", "SoundGoal", "UpdateSprite" if nes else "DrawPlayer")
    for index, (label, ending) in enumerate(zip(sections, after)):
        if source.count(label + ":\n") != 1 or source.count(ending + ":\n") != 1:
            raise NativeMediaSourceError("native original sound-cue handler missing")
        segment = source.split(label + ":\n", 1)[1].split(ending + ":\n", 1)[0]
        low_byte = programmed["events_low"][index]
        high_byte = programmed["events_high"][index]
        if nes:
            expected = (
                "lda #AUDIO_ENABLED\n"
                "    beq @silent\n"
                f"    lda #{low_byte}\n"
                "    sta $4006\n"
                f"    lda #{high_byte}\n"
                "    ora #$10\n"
                "    sta $4007\n"
                "@silent:\n"
                "    rts"
            )
        else:
            expected = (
                "ld a, AUDIO_ENABLED\n"
                "    or a\n"
                "    ret z\n"
                f"    ld a, {low_byte}\n"
                "    ldh [rNR23], a\n"
                f"    ld a, {high_byte}\n"
                "    or $80\n"
                "    ldh [rNR24], a\n"
                "    ret"
            )
        if segment.strip() != expected.strip():
            raise NativeMediaSourceError(
                "actual complete native cue handler differs from authored score"
            )

    body = {
        "schema": SCHEMA, "target": target, "world_digest": world,
        "source_assembly_sha256": sha256(source_bytes).hexdigest(),
        "source_pixel_parity_digest": parity["receipt_digest"],
        "original_base_tiles_sha256": sha256(original).hexdigest(),
        "original_hero_frames_sha256": sha256(animated).hexdigest(),
        "original_hero_frame_count": len(frames),
        "native_animation_ticks_per_frame": delay,
        "native_psg_score_digest": score.digest,
        "native_psg_enabled": density > 0,
        "native_music_notes": len(score.note_hz),
        "native_gameplay_cues": len(score.event_hz),
        "console_assembly_data_verified": True,
        "native_machine_code_executed": False,
        "audio_hardware_verified": False,
        "console_video_verified": False,
    }
    return {**body, "source_media_digest": canonical_digest(body)}


__all__ = ["NativeMediaSourceError", "inspect_native_source_media", "SCHEMA"]
