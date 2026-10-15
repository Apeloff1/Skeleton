"""Original ROM interpreter's internal DIV/TIMA timer source behavior.

No external ROMs, sound APIs or firmware. These tests use authored cartridge
bytes and the real GameBoyMachine's cycle-level timer state. They do not
certify DMG bus-access phase order, PPU timing, STOP or APU behavior.
"""
import unittest

from skeleton.jeeves.game_rom_runtime import GameBoyMachine, GameRomRuntimeError
from skeleton.testing.test_game_rom_mapper_expansion import synthetic_rom


def machine():
    return GameBoyMachine(synthetic_rom(0x00, 0, 0))


class DMGEdgeTimerCases(unittest.TestCase):
    def test_four_tac_rates_use_falling_edges_of_selected_div_bits(self):
        for selection, bit in ((0, 9), (1, 3), (2, 5), (3, 7)):
            with self.subTest(tac=selection):
                core = machine()
                core.divider = 0
                core.memory[0xFF05] = 0
                core.write(0xFF07, selection | 4)
                period = 1 << (bit + 1)
                core._advance(period - 1)
                self.assertEqual(core.read(0xFF05), 0)
                core._advance(1)
                self.assertEqual(core.read(0xFF05), 1)
                core._advance(period)
                self.assertEqual(core.read(0xFF05), 2)

    def test_div_reset_causes_increment_only_if_high_input_falls(self):
        core = machine()
        core.divider = 0
        core.write(0xFF07, 0x05)
        core.write(0xFF04, 0)
        self.assertEqual(core.read(0xFF05), 0)
        core.divider = 8
        core.write(0xFF04, 0)
        self.assertEqual(core.read(0xFF05), 1)
        self.assertEqual(core.read(0xFF04), 0)

    def test_tac_change_and_disable_can_pulse_tima_in_dmg(self):
        core = machine()
        core.divider = 8
        core.write(0xFF07, 5)  # selected bit 3 is HIGH
        core.write(0xFF07, 4)  # selected bit 9 is LOW
        self.assertEqual(core.read(0xFF05), 1)
        core.divider = 8
        core.write(0xFF07, 5)
        core.write(0xFF07, 0)  # DMG disable while input high
        self.assertEqual(core.read(0xFF05), 2)
        core.write(0xFF07, 0xFD)
        self.assertEqual(core.memory[0xFF07], 5)

    def test_tima_overflow_reloads_tma_after_four_t_cycles(self):
        core = machine()
        core.divider = 15
        core.write(0xFF07, 5)
        core.write(0xFF05, 255)
        core.write(0xFF06, 0x6A)
        core.memory[0xFF0F] &= ~4
        core._advance(1)
        self.assertEqual(core.timer_reload_delay, 4)
        self.assertEqual(core.read(0xFF05), 0)
        self.assertEqual(core.read(0xFF0F) & 4, 0)
        core._advance(3)
        self.assertEqual(core.timer_reload_delay, 1)
        self.assertEqual(core.read(0xFF05), 0)
        core._advance(1)
        self.assertEqual(core.read(0xFF05), 0x6A)
        self.assertEqual(core.read(0xFF0F) & 4, 4)

    def test_tima_write_cancels_pending_overflow(self):
        core = machine()
        core.divider = 15
        core.write(0xFF07, 5)
        core.write(0xFF05, 255)
        core._advance(1)
        self.assertEqual(core.timer_reload_delay, 4)
        core.write(0xFF05, 0x33)
        core._advance(4)
        self.assertEqual(core.read(0xFF05), 0x33)
        self.assertEqual(core.read(0xFF0F) & 4, 0)

    def test_tma_write_while_pending_controls_delayed_reload(self):
        core = machine()
        core.divider = 15
        core.write(0xFF07, 5)
        core.write(0xFF05, 255)
        core._advance(1)
        core.write(0xFF06, 0x92)
        core._advance(4)
        self.assertEqual(core.read(0xFF05), 0x92)
        self.assertEqual(core.read(0xFF0F) & 4, 4)

    def test_mid_overflow_snapshot_is_exactly_replayable(self):
        core = machine()
        core.divider = 15
        core.write(0xFF07, 5)
        core.write(0xFF05, 255)
        core._advance(1)
        snapshot = core.snapshot()
        self.assertEqual(snapshot["registers"]["timer_reload_delay"], 4)
        core._advance(16)
        first = core.snapshot()
        core.restore(snapshot)
        core._advance(16)
        self.assertEqual(core.snapshot(), first)

    def test_corrupt_pending_overflow_phase_is_rejected(self):
        core = machine()
        original = core.snapshot()
        original["registers"]["timer_reload_delay"] = 5
        import hashlib
        import json
        source = {key: value for key, value in original.items() if key != "state_digest"}
        original["state_digest"] = hashlib.sha256(
            json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        with self.assertRaises(GameRomRuntimeError):
            core.restore(original)


if __name__ == "__main__":
    unittest.main()
