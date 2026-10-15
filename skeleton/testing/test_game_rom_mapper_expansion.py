"""Source-level regression cases for experimental, original DMG ROM banking.

All ROMs are synthesized in-memory from non-copyrighted bytes. No commercial
cartridge, BIOS, or third-party game code is used. Do not mistake these cases
for hardware-timing/compatibility certification.
"""

import unittest

from skeleton.jeeves.game_rom_runtime import (
    GameBoyMachine,
    GameRomRuntimeError,
    inspect_dmg_cartridge,
)


def synthetic_rom(kind: int, size_code: int, ram_code: int) -> bytes:
    rom = bytearray(32768 << size_code)
    for bank in range(len(rom) // 16384):
        position = bank * 16384
        rom[position] = bank & 255
        rom[position + 1] = (bank >> 8) & 255
    rom[0x134:0x13A] = b"ORIGIN"
    rom[0x147] = kind
    rom[0x148] = size_code
    rom[0x149] = ram_code
    checksum = 0
    for byte in rom[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 255
    rom[0x14D] = checksum
    return bytes(rom)


class ExperimentalMbcExpansionTests(unittest.TestCase):
    def test_mbc3_selects_rom_bank_and_zero_maps_to_bank_one(self):
        machine = GameBoyMachine(synthetic_rom(0x11, 2, 0))
        self.assertEqual(machine.metadata["mapper"], "mbc3")
        machine.write(0x2000, 4)
        self.assertEqual(machine.read(0x4000), 4)
        machine.write(0x2000, 0)
        self.assertEqual(machine.read(0x4000), 1)

    def test_mbc3_ram_bank_switching_and_restore(self):
        machine = GameBoyMachine(synthetic_rom(0x13, 2, 3))
        machine.write(0x0000, 0x0A)
        machine.write(0x4000, 2)
        machine.write(0xA123, 0x66)
        snapshot = machine.snapshot()
        machine.write(0x4000, 1)
        self.assertEqual(machine.read(0xA123), 0)
        machine.restore(snapshot)
        self.assertEqual(machine.read(0xA123), 0x66)

    def test_mbc3_refuses_rtc_selection_and_rtc_cartridges(self):
        machine = GameBoyMachine(synthetic_rom(0x12, 1, 2))
        with self.assertRaises(GameRomRuntimeError):
            machine.write(0x4000, 8)
        for kind in (0x0F, 0x10):
            with self.subTest(kind=kind), self.assertRaises(GameRomRuntimeError):
                inspect_dmg_cartridge(synthetic_rom(kind, 1, 3))

    def test_mbc5_selects_ninth_rom_bank_bit(self):
        machine = GameBoyMachine(synthetic_rom(0x1B, 8, 4))
        self.assertEqual(machine.metadata["rom_banks"], 512)
        machine.write(0x2000, 0)
        machine.write(0x3000, 1)
        self.assertEqual(machine.read(0x4000), 0)
        self.assertEqual(machine.read(0x4001), 1)
        machine.write(0x2000, 255)
        self.assertEqual(machine.read(0x4000), 255)
        self.assertEqual(machine.read(0x4001), 1)

    def test_mbc5_allows_rom_bank_zero_and_restores_state(self):
        machine = GameBoyMachine(synthetic_rom(0x1B, 2, 4))
        machine.write(0x2000, 0)
        machine.write(0x3000, 0)
        snapshot = machine.snapshot()
        machine.write(0x2000, 3)
        self.assertEqual(machine.read(0x4000), 3)
        machine.restore(snapshot)
        self.assertEqual(machine.read(0x4000), 0)

    def test_mbc5_full_ram_bank_range(self):
        machine = GameBoyMachine(synthetic_rom(0x1B, 2, 4))
        machine.write(0x0000, 0x0A)
        machine.write(0x4000, 15)
        machine.write(0xA042, 0x9C)
        machine.write(0x4000, 0)
        self.assertEqual(machine.read(0xA042), 0)
        machine.write(0x4000, 15)
        self.assertEqual(machine.read(0xA042), 0x9C)

    def test_ram_is_disabled_until_enabled(self):
        machine = GameBoyMachine(synthetic_rom(0x1A, 2, 3))
        machine.write(0xA000, 0x42)
        self.assertEqual(machine.read(0xA000), 255)
        machine.write(0x0000, 0x0A)
        self.assertEqual(machine.read(0xA000), 0)

    def test_cartridge_geometry_refuses_impossible_ram_or_rom(self):
        for kind, size_code, ram_code in (
            (0x11, 7, 0),
            (0x13, 2, 4),
            (0x19, 2, 3),
            (0x1B, 2, 0),
            (0x1C, 2, 3),
        ):
            with self.subTest(kind=kind, rom=size_code, ram=ram_code), self.assertRaises(GameRomRuntimeError):
                inspect_dmg_cartridge(synthetic_rom(kind, size_code, ram_code))

    def test_snapshot_boundaries_reject_non_mbc5_bank_zero(self):
        machine = GameBoyMachine(synthetic_rom(0x13, 2, 3))
        snapshot = machine.snapshot()
        snapshot["registers"]["rom_bank"] = 0
        with self.assertRaises(GameRomRuntimeError):
            machine.restore(snapshot)


if __name__ == "__main__":
    unittest.main()
