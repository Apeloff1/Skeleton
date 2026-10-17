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
            valid = 0x8000 <= address <= 0xFFF1
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


def inspect_compiled_psg(
    rom: bytes, symbol_map: bytes, source_project: str | Path,
    *, target: str,
) -> dict:
    if target not in _TARGETS or type(rom) is not bytes:
        raise CompiledPSGError("known console target and actual ROM bytes required")
    source = Path(source_project)
    try:
        _header(_TARGETS[target], rom)
        manifest = json.loads(_regular(source / "manifest.json", 128_000))
        art = json.loads(
            _regular(source / "assets/metadata/descriptors.json", 128_000)
        )
        score = compose_native_psg(
            manifest["original_theme"], art["seed"], art["music_density"],
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CompiledPSGError("original sound provenance or cartridge invalid") from exc
    if (type(manifest) is not dict or type(art) is not dict
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
    if start < 0 or start + len(expected) > len(rom):
        raise CompiledPSGError("music bytes lie outside compiled cartridge")
    if rom[start:start + len(expected)] != expected:
        raise CompiledPSGError("actual cartridge PSG note tables differ from original score")
    body = {
        "schema": SCHEMA,
        "target": target,
        "source_score_digest": score.digest,
        "actual_rom_sha256": sha256(rom).hexdigest(),
        "actual_linker_sha256": sha256(symbol_map).hexdigest(),
        "native_music_prg_or_rom_offset": start,
        "notes_verified": 8,
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
