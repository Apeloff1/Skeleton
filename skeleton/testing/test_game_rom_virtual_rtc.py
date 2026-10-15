"""MBC3 deterministic virtual RTC source behavior; not battery wall-time accuracy.

Synthetic source-owned cartridge bytes only. The RTC counter progresses by
emulated CPU cycles, and its time basis is explicit in every restored state.
"""

import hashlib
import json
import unittest

from skeleton.jeeves.game_rom_runtime import (
    GameBoyMachine, GameRomRuntimeError, RTC_CYCLES_PER_SECOND,
    inspect_dmg_cartridge,
)
from skeleton.testing.test_game_rom_mapper_expansion import synthetic_rom


def clock_cartridge(kind=0x10, ram=3):
    return synthetic_rom(kind, 2, ram)


class DeterministicMbc3RTCRegression(unittest.TestCase):
    def test_timer_only_source_header_and_no_fake_external_ram(self):
        data = clock_cartridge(0x0F, 0)
        header = inspect_dmg_cartridge(data)
        self.assertEqual(header["mapper"], "mbc3")
        self.assertTrue(header["virtual_rtc"])
        self.assertEqual(header["ram_bytes"], 0)
        machine = GameBoyMachine(data)
        machine.write(0x0000, 10)
        machine.write(0x4000, 8)
        machine.write(0xA000, 17)
        self.assertEqual(machine.read(0xA000), 17)
        machine.write(0x4000, 0)
        self.assertEqual(machine.read(0xA000), 255)

    def test_latch_edge_holds_until_another_zero_to_one_transition(self):
        machine = GameBoyMachine(clock_cartridge())
        machine.write(0x0000, 10)
        machine.write(0x4000, 8)
        machine._rtc_advance(3 * RTC_CYCLES_PER_SECOND)
        machine.write(0x6000, 0)
        machine.write(0x6000, 1)
        self.assertEqual(machine.read(0xA000), 3)
        machine._rtc_advance(5 * RTC_CYCLES_PER_SECOND)
        self.assertEqual(machine.read(0xA000), 3)
        machine.write(0x6000, 1)
        self.assertEqual(machine.read(0xA000), 3)
        machine.write(0x6000, 0)
        machine.write(0x6000, 1)
        self.assertEqual(machine.read(0xA000), 8)

    def test_fractional_cpu_cycles_and_snapshot_replay(self):
        machine = GameBoyMachine(clock_cartridge())
        machine._rtc_advance(RTC_CYCLES_PER_SECOND - 12)
        snapshot = machine.snapshot()
        self.assertEqual(snapshot["schema_version"], 2)
        self.assertEqual(snapshot["rtc"]["cycle_remainder"], RTC_CYCLES_PER_SECOND - 12)
        machine._advance(20)
        self.assertEqual(machine.rtc_regs[0], 1)
        observed = machine.snapshot()
        machine.restore(snapshot)
        machine._advance(20)
        self.assertEqual(machine.snapshot(), observed)

    def test_halt_resume_and_512_day_sticky_carry(self):
        machine = GameBoyMachine(clock_cartridge())
        machine.write(0x0000, 10)
        for selector, value in ((8, 59), (9, 59), (10, 23), (11, 255), (12, 1)):
            machine.write(0x4000, selector)
            machine.write(0xA000, value)
        machine.write(0x4000, 12)
        machine.write(0xA000, 0x41)  # Halt plus day bit eight.
        machine._rtc_advance(10 * RTC_CYCLES_PER_SECOND)
        self.assertEqual(machine.rtc_regs[:4], [59, 59, 23, 255])
        machine.write(0xA000, 0x01)  # Resume before a rollover.
        machine._rtc_advance(RTC_CYCLES_PER_SECOND)
        self.assertEqual(machine.rtc_regs[:4], [0, 0, 0, 0])
        self.assertEqual(machine.rtc_regs[4], 0x80)
        machine._rtc_advance(RTC_CYCLES_PER_SECOND)
        self.assertEqual(machine.rtc_regs[4], 0x80)
        machine.write(0xA000, 0)
        self.assertEqual(machine.rtc_regs[4], 0)

    def test_rtc_free_mbc3_refuses_clock_register(self):
        machine = GameBoyMachine(synthetic_rom(0x13, 2, 3))
        machine.write(0x0000, 10)
        with self.assertRaises(GameRomRuntimeError):
            machine.write(0x4000, 8)

    def test_snapshot_rejects_corrupted_latched_or_live_clock(self):
        machine = GameBoyMachine(clock_cartridge())
        snapshot = machine.snapshot()
        for key, invalid in (("live", [60, 0, 0, 0, 0]),
                             ("latched", [0, 0, 24, 0, 0]),
                             ("cycle_remainder", RTC_CYCLES_PER_SECOND),
                             ("previous_latch_bit", 3)):
            with self.subTest(key=key):
                bad = json.loads(json.dumps(snapshot))
                bad["rtc"][key] = invalid
                claimed = dict(bad)
                claimed.pop("state_digest")
                bad["state_digest"] = hashlib.sha256(
                    json.dumps(claimed, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
                ).hexdigest()
                with self.assertRaises(GameRomRuntimeError):
                    machine.restore(bad)

    def test_header_rejects_wrong_timer_ram_geometry(self):
        for kind, ram in ((0x0F, 3), (0x10, 0)):
            with self.subTest(kind=kind):
                with self.assertRaises(GameRomRuntimeError):
                    inspect_dmg_cartridge(clock_cartridge(kind, ram))


if __name__ == "__main__":
    unittest.main()
