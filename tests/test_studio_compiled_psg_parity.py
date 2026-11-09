"""Actual compiled GB/GBC/NES PRG bytes must retain authored original music.

The ROM bytes in this suite are synthetic compiler boundary fixtures, not
evidence of an installed RGBDS/cc65 toolchain or audio hardware playback.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.native_game_cli import build_game
from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_compiled_psg_parity import (
    CompiledPSGError, inspect_compiled_psg, _effect_bytes,
)
from skeleton.ai.game_builder.studio_native_psg import (
    compose_native_psg, console_psg_registers,
)


def cartridge(target: str, notes: bytes, *, density: int = 2) -> tuple[bytes, bytes, int]:
    if len(notes) != 16:
        raise ValueError("authored eight-note low/high tables required")
    period = console_psg_registers(
        compose_native_psg("forest", 733, density), target,
    )
    if target == "nintendo_famicom":
        program = bytearray(32768)
        program[0x100:0x110] = notes
        for index in range(3):
            start = 0x130 + 17 * index
            program[start:start + 17] = _effect_bytes(
                target, enabled=density > 0,
                low=period["events_low"][index],
                high=period["events_high"][index],
            )
        rom = (
            b"NES\x1a" + bytes((2, 1)) + bytes(10)
            + bytes(program) + bytes(8192)
        )
        symbols = (
            b"al 008100 .OriginalMusicLow\nal 008108 .OriginalMusicHigh\n"
            b"al 008130 .SoundPickup\nal 008141 .SoundHazard\n"
            b"al 008152 .SoundGoal\n"
        )
        return rom, symbols, 16 + 0x100
    program = bytearray(32768)
    program[0x280:0x290] = notes
    for index in range(3):
        start = 0x2A0 + 15 * index
        program[start:start + 15] = _effect_bytes(
            target, enabled=density > 0,
            low=period["events_low"][index],
            high=period["events_high"][index],
        )
    if target == "nintendo_game_boy_color":
        program[0x143] = 0x80
    check = 0
    for item in program[0x134:0x14D]:
        check = (check - item - 1) & 255
    program[0x14D] = check
    return (
        bytes(program),
        (
            b"00:0280 OriginalMusicLow\n00:0288 OriginalMusicHigh\n"
            b"00:02a0 SoundPickup\n00:02af SoundHazard\n"
            b"00:02be SoundGoal\n"
        ),
        0x280,
    )


class OriginalCompiledPSGTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.rights = self.base / "rights.txt"
        self.rights.write_text(
            "All sound and characters are original content owned by this project",
            encoding="utf-8",
        )

    def source(self, target: str, density: int) -> Path:
        folder = self.base / f"{target}-{density}"
        result = build_game(
            target=target, basis="bandai_wonderswan",
            project_id="original-psg-rom", title="Sound in Native ROM",
            seed=733, width=11, height=11, levels=1,
            collectibles=1, hazards=0, health=4,
            rights_evidence=self.rights,
            creative_identity=("original-art", "independently-authored-sound"),
            output=folder, authorized=True, theme="forest",
            studio_art=ArtDirection(
                seed=733, style="organic", animation_frames=2,
                music_density=density, parallax_layers=0,
            ),
        )
        self.assertFalse(result["native_binary_built"])
        return folder

    def test_original_score_bytes_survive_independent_compiled_rom_and_linker(self):
        for target in (
            "nintendo_game_boy", "nintendo_game_boy_color",
            "nintendo_famicom",
        ):
            for density in (0, 3):
                with self.subTest(target=target, density=density):
                    source = self.source(target, density)
                    score = compose_native_psg("forest", 733, density)
                    registers = console_psg_registers(score, target)
                    raw = bytes((
                        *registers["notes_low"], *registers["notes_high"],
                    ))
                    rom, symbols, _ = cartridge(target, raw, density=density)
                    evidence = inspect_compiled_psg(
                        rom, symbols, source, target=target,
                    )
                    self.assertEqual(evidence["notes_verified"], 8)
                    self.assertEqual(evidence["gameplay_sound_cue_routines_verified"], 3)
                    self.assertEqual(len(evidence["compiled_gameplay_cues_sha256"]), 64)
                    self.assertEqual(evidence["source_score_digest"], score.digest)
                    self.assertEqual(evidence["verified_note_table_sha256"],
                                     __import__("hashlib").sha256(raw).hexdigest())
                    self.assertEqual(len(evidence["compiled_score_digest"]), 64)
                    self.assertFalse(evidence["actual_emulator_audio_executed"])
                    self.assertFalse(evidence["hardware_audio_sampled"])
                    self.assertFalse(evidence["pcm_identity_claimed"])

    def test_compiled_music_byte_corruption_is_not_hidden_by_valid_header(self):
        for target in ("nintendo_game_boy", "nintendo_game_boy_color",
                       "nintendo_famicom"):
            with self.subTest(target=target):
                source = self.source(target, 3)
                registers = console_psg_registers(
                    compose_native_psg("forest", 733, 3), target,
                )
                rom, symbols, offset = cartridge(
                    target, bytes((
                        *registers["notes_low"], *registers["notes_high"],
                    )), density=3,
                )
                for position in (0, 7, 8, 15):
                    changed = bytearray(rom)
                    changed[offset + position] ^= 0x01
                    with self.assertRaises(CompiledPSGError):
                        inspect_compiled_psg(
                            bytes(changed), symbols, source, target=target,
                        )

    def test_compiled_sound_machine_code_must_match_all_three_original_game_events(self):
        for target in ("nintendo_game_boy", "nintendo_game_boy_color",
                       "nintendo_famicom"):
            with self.subTest(target=target):
                source = self.source(target, 3)
                score = console_psg_registers(
                    compose_native_psg("forest", 733, 3), target,
                )
                rom, symbols, _ = cartridge(
                    target, bytes((*score["notes_low"], *score["notes_high"])),
                    density=3,
                )
                length = 17 if target == "nintendo_famicom" else 15
                first = 16 + 0x130 if target == "nintendo_famicom" else 0x2A0
                for index in range(3):
                    for at in (0, 1, 3, 5, length - 1):
                        forged = bytearray(rom)
                        forged[first + index * length + at] ^= 1
                        with self.subTest(cue=index, opcode=at):
                            with self.assertRaises(CompiledPSGError):
                                inspect_compiled_psg(
                                    bytes(forged), symbols, source, target=target,
                                )

    def test_generated_native_cue_opcode_layout_is_platform_specific(self):
        # Independent instruction-level assertions, not merely a copy of
        # the expected score table or a digest of a synthetic ROM.
        gb = _effect_bytes(
            "nintendo_game_boy", enabled=True, low=0x34, high=0x04,
        )
        self.assertEqual(gb, bytes.fromhex(
            "3E 01 B7 C8 3E 34 E0 18 3E 04 F6 80 E0 19 C9"
        ))
        nes = _effect_bytes(
            "nintendo_famicom", enabled=True, low=0x34, high=0x04,
        )
        self.assertEqual(nes, bytes.fromhex(
            "A9 01 F0 0C A9 34 8D 06 40 A9 04 09 10 8D 07 40 60"
        ))

    def test_wrong_symbol_bank_duplicate_missing_or_overlapping_tables_fail(self):
        source = self.source("nintendo_game_boy", 2)
        periods = console_psg_registers(
            compose_native_psg("forest", 733, 2), "nintendo_game_boy",
        )
        rom, symbols, _ = cartridge(
            "nintendo_game_boy",
            bytes((*periods["notes_low"], *periods["notes_high"])),
        )
        for invalid in (
            b"",
            b"00:0280 OriginalMusicLow\n",
            symbols + b"00:0280 OriginalMusicLow\n",
            b"01:4280 OriginalMusicLow\n01:4288 OriginalMusicHigh\n",
            b"00:0280 OriginalMusicLow\n00:0287 OriginalMusicHigh\n",
            b"00:3FF8 OriginalMusicLow\n00:4000 OriginalMusicHigh\n",
        ):
            with self.subTest(symbols=invalid), self.assertRaises(CompiledPSGError):
                inspect_compiled_psg(
                    rom, invalid, source, target="nintendo_game_boy",
                )

    def test_nes_vector_page_and_other_bank_are_not_music_tables(self):
        source = self.source("nintendo_famicom", 2)
        periods = console_psg_registers(
            compose_native_psg("forest", 733, 2), "nintendo_famicom",
        )
        rom, _, _ = cartridge(
            "nintendo_famicom",
            bytes((*periods["notes_low"], *periods["notes_high"])),
        )
        for symbols in (
            b"al 00FFF0 .OriginalMusicLow\nal 00FFF8 .OriginalMusicHigh\n",
            b"al 007100 .OriginalMusicLow\nal 007108 .OriginalMusicHigh\n",
            b"al 008100 .OriginalMusicLow\nal 008109 .OriginalMusicHigh\n",
            b"al 008100 .OriginalMusicLow\nal 008108 .OriginalMusicHigh\n"
            b"al 008100 .OriginalMusicLow\n",
        ):
            with self.subTest(symbols=symbols), self.assertRaises(CompiledPSGError):
                inspect_compiled_psg(
                    rom, symbols, source, target="nintendo_famicom",
                )
        # An NROM-128 16KB cartridge is not the original NROM-256 engine.
        old = bytearray(rom)
        old[4] = 1
        with self.assertRaises(CompiledPSGError):
            inspect_compiled_psg(
                bytes(old), b"al 008100 .OriginalMusicLow\nal 008108 .OriginalMusicHigh\n",
                source, target="nintendo_famicom",
            )


if __name__ == "__main__":
    unittest.main()
