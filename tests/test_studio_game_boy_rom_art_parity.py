"""The actual GB/GBC cartridge must contain the six original authored tiles.

This synthetic ROM test verifies compiled-byte/linker-map integrity only;
it does not substitute for executing the ROM in PyBoy or physical hardware.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.studio_game_boy_rom_art_parity import (
    GameBoyROMArtError, inspect_compiled_game_boy_art, parse_game_boy_tile_labels,
)


LABELS = b"00:0200 Tiles\n00:0260 TilesEnd\n"


def make_rom(art: bytes, *, color: bool = False) -> bytes:
    data = bytearray(32768)
    data[0x200:0x260] = art
    if color:
        data[0x143] = 0x80
    check = 0
    for item in data[0x134:0x14D]:
        check = (check - item - 1) & 255
    data[0x14D] = check
    return bytes(data)


class CompiledGameBoySpriteParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        (self.project / "assets/tiles").mkdir(parents=True)
        self.authored = bytes(range(96))
        (self.project / "assets/tiles/runtime.bin").write_bytes(self.authored)

    def test_rgbds_bank0_linker_symbols_bind_exact_original_tiles(self):
        self.assertEqual(parse_game_boy_tile_labels(LABELS), (0x200, 0x260))
        for color in (False, True):
            with self.subTest(color=color):
                rom = make_rom(self.authored, color=color)
                outcome = inspect_compiled_game_boy_art(
                    rom, LABELS, self.project, color=color,
                )
                self.assertEqual(outcome["tile_byte_count"], 96)
                self.assertEqual(outcome["matched_indexed_pixels"], 384)
                self.assertEqual(outcome["source_tiles_sha256"],
                                 sha256(self.authored).hexdigest())
                self.assertEqual(outcome["compiled_rom_sha256"],
                                 sha256(rom).hexdigest())
                self.assertFalse(outcome["emulated_lcd_pixels_verified"])
                self.assertFalse(outcome["release_authorized"])

    def test_compiled_sprite_mutation_is_fatal_even_if_rom_header_is_valid(self):
        for color in (False, True):
            with self.subTest(color=color):
                wrong = bytearray(make_rom(self.authored, color=color))
                wrong[0x225] ^= 1
                with self.assertRaises(GameBoyROMArtError):
                    inspect_compiled_game_boy_art(
                        bytes(wrong), LABELS, self.project, color=color,
                    )

    def test_missing_duplicate_out_of_rom_bank_or_forged_tile_labels_fail(self):
        for invalid in (
            b"",
            b"00:0200 Tiles\n",
            LABELS + b"00:0200 Tiles\n",
            b"01:4000 Tiles\n01:4060 TilesEnd\n",
            b"00:c000 Tiles\n00:c060 TilesEnd\n",
            b"00:0200 Tiles\n00:0261 TilesEnd\n",
            b"00:0300 Tiles\n00:0360 TilesEnd\n",
        ):
            with self.subTest(invalid=invalid):
                try:
                    labels = parse_game_boy_tile_labels(invalid)
                except GameBoyROMArtError:
                    continue
                with self.assertRaises(GameBoyROMArtError):
                    inspect_compiled_game_boy_art(
                        make_rom(self.authored), invalid, self.project,
                    )

    def test_original_source_png_tile_bundle_mutation_is_not_accepted(self):
        rom = make_rom(self.authored)
        (self.project / "assets/tiles/runtime.bin").write_bytes(b"wrong")
        with self.assertRaises(GameBoyROMArtError):
            inspect_compiled_game_boy_art(rom, LABELS, self.project)


if __name__ == "__main__":
    unittest.main()
