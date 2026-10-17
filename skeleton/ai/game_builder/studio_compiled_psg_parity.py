"""Attest source-authored GB/CGB/NES PSG note tables in the *compiled* ROM.

A header-valid cartridge may have mutated note bytes or changed linker
placement. These checks read the actual RGBLINK / ld65 symbol map and
cartridge bytes; a source text or manifest digest alone is insufficient.
No claim of audible hardware output, DAC equivalence or PCM identity.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from .contracts import canonical_digest
from .studio_build_qualification import _header, _regular
from .studio_native_psg import compose_native_psg, console_psg_registers
from .studio_pixel_parity import _game_json
from .studio_runtime_qualification import _inputs

SCHEMA = "skeleton.game_builder.compiled_original_psg_parity.v1"
_TARGETS = {
    "nintendo_game_boy": "gb",
    "nintendo_game_boy_color": "gbc",
    "nintendo_famicom": "nes",
}
_SYMBOLS = ("OriginalMusicLow", "OriginalMusicHigh")


class CompiledPSGError(ValueError):
    """Actual compiled cartridge music differs from its original composition."""


def _music_addresses(raw: bytes, target: str) -> tuple[int, int]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 128_000:
        raise CompiledPSGError("bounded actual linker symbol map required")
    try:
        source = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CompiledPSGError("non-ASCII native linker address map") from exc
    found: dict[str, int] = {}
    for line in source.splitlines():
        line = line.strip()
        if target == "nintendo_famicom":
            match = re.fullmatch(
                r"al ([0-9A-Fa-f]{6}) \.([A-Za-z][A-Za-z0-9_]*)",
                line,
            )
            if match is None:
                continue
            label = match[2]
            address = int(match[1], 16)
            valid = 0x8000 <= address <= 0xFFEA
        else:
            match = re.fullmatch(
                r"([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})\s+([A-Za-z][A-Za-z0-9_]*)",
                line,
            )
            if match is None:
                continue
            label = match[3]
            bank, address = int(match[1], 16), int(match[2], 16)
            valid = bank == 0 and 0x0150 <= address <= 0x3FF0
        if label not in _SYMBOLS:
            continue
        if label in found or not valid:
            raise CompiledPSGError("music label duplicate or outside fixed cartridge bank")
        found[label] = address
    if set(found) != set(_SYMBOLS):
        raise CompiledPSGError("original music table linker labels are missing")
    first, second = found[_SYMBOLS[0]], found[_SYMBOLS[1]]
    if second != first + 8:
        raise CompiledPSGError("exact eight-note low/high source layout changed")
    return first, second


_CUES = ("SoundPickup", "SoundHazard", "SoundGoal")


def _cue_locations(raw: bytes, target: str, size: int) -> tuple[int, int, int]:
    """Read three linker-owned fixed CPU routines, without searching ROM bytes."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 128_000:
        raise CompiledPSGError("bounded sound effect linker labels required")
    try:
        source = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CompiledPSGError("compiled sound effect address map is not ASCII") from exc
    addresses: dict[str, int] = {}
    for line in source.splitlines():
        line = line.strip()
        if target == "nintendo_famicom":
            match = re.fullmatch(
                r"al ([0-9A-Fa-f]{6}) \.([A-Za-z][A-Za-z0-9_]*)", line,
            )
            if match is None:
                continue
            address, label = int(match[1], 16), match[2]
            valid = 0x8000 <= address <= 0xFFFA - size
        else:
            match = re.fullmatch(
                r"([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})\s+([A-Za-z][A-Za-z0-9_]*)",
                line,
            )
            if match is None:
                continue
            address, label = int(match[2], 16), match[3]
            valid = int(match[1], 16) == 0 and 0x0150 <= address <= 0x4000 - size
        if label not in _CUES:
            continue
        if label in addresses or not valid:
            raise CompiledPSGError("native sound cue label duplicate or outside code bank")
        addresses[label] = address
    if set(addresses) != set(_CUES):
        raise CompiledPSGError("compiler omitted at least one source-authored sound effect")
    locations = tuple(addresses[key] for key in _CUES)
    if not (locations[1] - locations[0] == size
            and locations[2] - locations[1] == size):
        raise CompiledPSGError("machine sound routines lost their fixed source order")
    return locations


def _effect_bytes(target: str, *, enabled: bool, low: int, high: int) -> bytes:
    """Exact unoptimized instruction encoding for the emitted console sources."""
    if target == "nintendo_famicom":
        # LDA #enable; BEQ +12; LDA #low; STA $4006; LDA #high;
        # ORA #$10; STA $4007; RTS. No skipped effects or hidden shell code.
        return bytes((
            0xA9, int(enabled), 0xF0, 0x0C,
            0xA9, low, 0x8D, 0x06, 0x40,
            0xA9, high, 0x09, 0x10, 0x8D, 0x07, 0x40, 0x60,
        ))
    # LD A,#enable; OR A; RET Z; LD A,#low; LDH [$FF18],A;
    # LD A,#high; OR $80; LDH [$FF19],A; RET.
    return bytes((
        0x3E, int(enabled), 0xB7, 0xC8,
        0x3E, low, 0xE0, 0x18,
        0x3E, high, 0xF6, 0x80, 0xE0, 0x19, 0xC9,
    ))


def inspect_compiled_psg(
    rom: bytes, symbol_map: bytes, source_project: str | Path,
    *, target: str,
) -> dict:
    if target not in _TARGETS or type(rom) is not bytes:
        raise CompiledPSGError("known console target and actual ROM bytes required")
    source = Path(source_project)
    try:
        _header(_TARGETS[target], rom)
        if target == "nintendo_famicom" and rom[4] != 2:
            raise CompiledPSGError("original NROM-256 requires exactly two PRG ROM banks")
        manifest = json.loads(_regular(source / "manifest.json", 128_000))
        art = json.loads(
            _regular(source / "assets/metadata/descriptors.json", 128_000)
        )
        _, _, original_world = _inputs(source / "engines")
        game = _game_json(
            _regular(source / "engines/index.html", 2_000_000).decode("utf-8")
        )
        original_theme = game["intent"]["theme"]
        score = compose_native_psg(
            original_theme, art["seed"], art["music_density"],
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CompiledPSGError("original sound provenance or cartridge invalid") from exc
    if (type(manifest) is not dict or type(art) is not dict
            or manifest.get("world_digest") != original_world
            or art.get("world_digest") != original_world
            or game.get("world_digest") != original_world
            or art.get("target") != target
            or manifest.get("native_psg_score_digest") != score.digest
            or manifest.get("original_native_psg_integrated")
            != (score.density > 0)):
        raise CompiledPSGError("soundtrack not bound to exact original game and target")

    periods = console_psg_registers(score, target)
    low, high = _music_addresses(symbol_map, target)
    start = (16 + low - 0x8000
             if target == "nintendo_famicom" else low)
    expected = bytes((*periods["notes_low"], *periods["notes_high"]))
    prg_end = (
        16 + rom[4] * 16_384 if target == "nintendo_famicom"
        else min(0x4000, len(rom))
    )
    if start < 0 or start + len(expected) > prg_end:
        raise CompiledPSGError("music bytes lie outside actual PRG/ROM0 bank")
    if rom[start:start + len(expected)] != expected:
        raise CompiledPSGError("actual cartridge PSG note tables differ from original score")
    cue_periods = console_psg_registers(score, target)
    cue_length = 17 if target == "nintendo_famicom" else 15
    cue_addresses = _cue_locations(symbol_map, target, cue_length)
    compiled_cues = bytearray()
    for index, cpu_address in enumerate(cue_addresses):
        location = (
            16 + cpu_address - 0x8000
            if target == "nintendo_famicom" else cpu_address
        )
        expected_code = _effect_bytes(
            target, enabled=score.density > 0,
            low=cue_periods["events_low"][index],
            high=cue_periods["events_high"][index],
        )
        if (location < 0 or location + cue_length > prg_end
                or rom[location:location + cue_length] != expected_code):
            raise CompiledPSGError(
                "compiled gameplay sound handler no longer writes its original APU cue"
            )
        compiled_cues.extend(expected_code)
    body = {
        "schema": SCHEMA,
        "target": target,
        "source_score_digest": score.digest,
        "actual_rom_sha256": sha256(rom).hexdigest(),
        "actual_linker_sha256": sha256(symbol_map).hexdigest(),
        "native_music_prg_or_rom_offset": start,
        "notes_verified": 8,
        "gameplay_sound_cue_routines_verified": 3,
        "compiled_gameplay_cues_sha256": sha256(compiled_cues).hexdigest(),
        "verified_note_table_sha256": sha256(expected).hexdigest(),
        "original_music_enabled": score.density > 0,
        "hardware_audio_sampled": False,
        "actual_emulator_audio_executed": False,
        "pcm_identity_claimed": False,
        "release_qualified": False,
    }
    return {**body, "compiled_score_digest": canonical_digest(body)}


__all__ = [
    "CompiledPSGError", "inspect_compiled_psg", "SCHEMA",
]
