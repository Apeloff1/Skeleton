"""DMG FF01/FF02 serial port source-clock, disconnected line and restore.

Synthetic original Game Boy cartridges only. No native multiplayer/link peer,
CGB double-speed, cable-edge analog behavior or production model changes.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from skeleton.jeeves.game_rom_runtime import (
    GameBoyMachine, GameRomRuntimeError, SERIAL_INTERNAL_BIT_CYCLES,
)
from scripts.audit_original_gameboy_cpu_opcodes import _cartridge


def make_machine():
    return GameBoyMachine(_cartridge(0))


class DMGSerialPortSourceTests(unittest.TestCase):
    def test_8_internal_bits_need_exactly_4096_real_t_cycles(self):
        m = make_machine()
        m.memory[0xFF0F] &= ~8
        m.write(0xFF01, 0x5A)
        m.write(0xFF02, 0x81)
        self.assertEqual(m.read(0xFF02), 0xFF)
        m._advance(511)
        self.assertEqual(m.read(0xFF01), 0x5A)
        self.assertEqual(m.serial_bits, 0)
        self.assertEqual(m.serial_phase, 511)
        m._advance(1)
        self.assertEqual(m.read(0xFF01), 0xB5)
        self.assertEqual(m.serial_bits, 1)
        self.assertEqual(m.serial_phase, 0)
        m._advance(SERIAL_INTERNAL_BIT_CYCLES * 7 - 1)
        self.assertEqual(m.read(0xFF0F) & 8, 0)
        self.assertTrue(m.serial_active)
        m._advance(1)
        self.assertEqual(m.read(0xFF01), 0xFF)
        self.assertFalse(m.serial_active)
        self.assertEqual(m.read(0xFF02) & 0x80, 0)
        self.assertEqual(m.read(0xFF0F) & 8, 8)
        self.assertEqual(m.serial_bits, 0)

    def test_external_clock_without_peer_never_completes(self):
        m = make_machine()
        m.write(0xFF01, 0x37)
        m.write(0xFF02, 0x80)
        m._advance(8192)
        self.assertEqual(m.read(0xFF01), 0x37)
        self.assertEqual(m.read(0xFF02) & 0x81, 0x80)
        self.assertTrue(m.serial_active)
        self.assertEqual(m.serial_phase, 0)
        self.assertEqual(m.memory[0xFF0F] & 8, 0)

    def test_restart_source_serial_control_resets_phase(self):
        m = make_machine()
        m.write(0xFF01, 0x00)
        m.write(0xFF02, 0x81)
        m._advance(1500)
        self.assertEqual(m.serial_bits, 2)
        m.write(0xFF02, 0x81)
        self.assertEqual((m.serial_bits, m.serial_phase), (0, 0))
        m._advance(512)
        self.assertEqual(m.serial_bits, 1)
        self.assertEqual(m.read(0xFF01), 0x07)

    def test_source_rewind_mid_serial_byte_produces_identical_interrupt(self):
        m = make_machine()
        m.write(0xFF01, 0xA6)
        m.write(0xFF02, 0x81)
        m._advance(1373)
        source = m.snapshot()
        self.assertGreater(source["registers"]["serial_phase"], 0)
        m._advance(4096 - 1373)
        finish = m.snapshot()
        m.restore(source)
        self.assertEqual(m.snapshot(), source)
        m._advance(4096 - 1373)
        self.assertEqual(m.snapshot(), finish)
        self.assertEqual(m.memory[0xFF0F] & 8, 8)

    def test_stop_suspends_serial_oscillator_halt_does_not(self):
        m = make_machine()
        m.write(0xFF01, 0)
        m.write(0xFF02, 0x81)
        m.stopped = True
        for _ in range(20):
            m.instruction()
        self.assertEqual(m.serial_phase, 0)
        m.stopped = False
        m.halted = True
        for _ in range(20):
            m.instruction()
        self.assertEqual(m.serial_phase, 80)

    def test_mid_transfer_SB_rewrite_fails_closed(self):
        m = make_machine()
        m.write(0xFF02, 0x81)
        with self.assertRaises(GameRomRuntimeError):
            m.write(0xFF01, 0xFF)

    def test_invalid_phase_and_active_register_claims_rejected(self):
        m = make_machine()
        m.write(0xFF01, 0x77)
        m.write(0xFF02, 0x81)
        snapshot = m.snapshot()
        for key, value in (("serial_phase", 512), ("serial_bits", 8)):
            with self.subTest(key=key):
                changed = json.loads(json.dumps(snapshot))
                changed["registers"][key] = value
                source = {k: v for k, v in changed.items() if k != "state_digest"}
                changed["state_digest"] = hashlib.sha256(
                    json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
                ).hexdigest()
                with self.assertRaises(GameRomRuntimeError):
                    m.restore(changed)

    def test_full_reset_cancels_inflight_serial_control(self):
        m = make_machine()
        m.write(0xFF01, 0xA5)
        m.write(0xFF02, 0x81)
        m._advance(1337)
        m.write(0xFF02, 0x00)
        self.assertFalse(m.serial_active)
        self.assertEqual((m.serial_bits, m.serial_phase), (0, 0))
        self.assertEqual(m.read(0xFF0F) & 8, 0)


if __name__ == "__main__":
    unittest.main()
