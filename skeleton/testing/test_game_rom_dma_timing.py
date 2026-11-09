"""Bounded source-accurate OAM sprite DMA timing and native snapshot regression.

Tests operate on original synthetic cartridge bytes with the experimental
DMG machine. They do not certify CGB, OAM/VRAM bus conflicts, PPU fetcher
phase, unsupported source pages or complete hardware accuracy.
"""

import hashlib
import json
import unittest

from skeleton.jeeves.game_rom_runtime import GameBoyMachine, GameRomRuntimeError
from skeleton.testing.test_game_rom_mapper_expansion import synthetic_rom


def make_machine():
    machine = GameBoyMachine(synthetic_rom(0x00, 0, 0))
    for i in range(160):
        machine.memory[0xC000 + i] = (0x80 + i) & 255
        machine.memory[0xD000 + i] = (0x40 + i) & 255
    return machine


def resign(snapshot):
    payload = {k: v for k, v in snapshot.items() if k != "state_digest"}
    snapshot["state_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return snapshot


class ClockedOAMSourceDMATests(unittest.TestCase):
    def test_no_immediate_copy_and_exact_startup_4t_plus_one_byte_every_4t(self):
        m = make_machine()
        m.write(0xFF46, 0xC0)
        self.assertTrue(m.dma_active)
        self.assertEqual(m.dma_index, 0)
        self.assertEqual(m.memory[0xFE00], 0)
        m._advance(4)
        self.assertEqual(m.dma_startup, 0)
        self.assertEqual(m.dma_index, 0)
        m._advance(3)
        self.assertEqual(m.memory[0xFE00], 0)
        m._advance(1)
        self.assertEqual(m.memory[0xFE00], 0x80)
        self.assertEqual(m.dma_index, 1)
        self.assertTrue(m.dma_active)
        m._advance(4 * 158)
        self.assertEqual(m.dma_index, 159)
        self.assertEqual(m.memory[0xFE9E], (0x80 + 158) & 255)
        self.assertTrue(m.dma_active)
        m._advance(4)
        self.assertFalse(m.dma_active)
        self.assertEqual(m.dma_index, 160)
        self.assertEqual(m.memory[0xFE9F], (0x80 + 159) & 255)

    def test_source_reads_take_place_during_dma_not_when_ff46_is_written(self):
        m = make_machine()
        m.write(0xFF46, 0xC0)
        m.memory[0xC000] = 0x37
        m._advance(8)
        self.assertEqual(m.memory[0xFE00], 0x37)

    def test_restart_changes_source_and_resets_byte_phase(self):
        m = make_machine()
        m.write(0xFF46, 0xC0)
        m._advance(4 + 4 * 12)
        self.assertEqual(m.dma_index, 12)
        m.write(0xFF46, 0xD0)
        self.assertEqual(m.dma_index, 0)
        self.assertEqual(m.dma_startup, 4)
        m._advance(4 + 4 * 160)
        self.assertFalse(m.dma_active)
        self.assertEqual(m.memory[0xFE00], 0x40)
        self.assertEqual(m.memory[0xFE9F], (0x40 + 159) & 255)

    def test_scanlines_use_oam_at_their_real_tick_not_future_dma_state(self):
        m = make_machine()
        m.line_cycles = 455
        captures = []
        # Focus this regression on the clock coupling itself; the real
        # sprite raster renderer has its own tile and priority contracts.
        m._draw_line = lambda line: captures.append((line, m.dma_index))
        m.write(0xFF46, 0xC0)
        m._advance(457)  # One call spans TWO line endings.
        self.assertEqual(captures, [(0, 0), (1, 113)])
        self.assertTrue(m.dma_active)

    def test_ppu_STAT_modes_are_sampled_during_multi_line_cpu_tick_blocks(self):
        m = make_machine()
        captured_modes = set()
        original_read = m.read

        def sampled_read(address):
            result = original_read(address)
            if address == 0xFF41:
                captured_modes.add(result & 3)
            return result

        m.read = sampled_read
        m._advance(456)
        self.assertTrue({0, 2, 3}.issubset(captured_modes))
        self.assertEqual(m.memory[0xFF44], 1)

    def test_inflight_oam_dma_savestate_replays_frame_and_bus_exactly(self):
        m = make_machine()
        m.write(0xFF46, 0xC0)
        m._advance(4 + 4 * 25 + 2)
        self.assertTrue(m.dma_active)
        self.assertEqual(m.dma_index, 25)
        self.assertEqual(m.dma_tcycles, 2)
        prior = m.snapshot()
        m._advance(4 * 135 - 2)
        completed = m.snapshot()
        self.assertFalse(m.dma_active)
        m.restore(prior)
        self.assertEqual(m.snapshot(), prior)
        m._advance(4 * 135 - 2)
        self.assertEqual(m.snapshot(), completed)

    def test_stop_pauses_dma_until_oscillator_runs_again(self):
        m = make_machine()
        m.write(0xFF46, 0xC0)
        m.stopped = True
        for _ in range(5):
            m.instruction()
        self.assertEqual(m.dma_index, 0)
        self.assertEqual(m.dma_startup, 4)
        m.set_buttons(("a",))
        self.assertFalse(m.stopped)
        m._advance(8)
        self.assertEqual(m.dma_index, 1)

    def test_HRAM_CPU_reads_of_WRAM_are_blocked_but_internal_DMA_still_reads_it(self):
        m = make_machine()
        m.pc = 0xFF80
        m.memory[0xFF80] = 0x7E  # LD A,(HL)
        m._set_pair(2, 0xC000)
        m.a = 0
        m.write(0xFF46, 0xC0)
        m.instruction()
        self.assertEqual(m.a, 0xFF)
        self.assertEqual(m.memory[0xFE00], 0x80)
        self.assertFalse(m._cpu_bus_active)

    def test_HRAM_CPU_write_to_external_bus_during_DMA_has_no_effect(self):
        m = make_machine()
        m.pc = 0xFF80
        m.memory[0xFF80] = 0x77  # LD (HL),A
        m.a = 0x36
        m._set_pair(2, 0xC100)
        m.memory[0xC100] = 0x91
        m.write(0xFF46, 0xC0)
        m.instruction()
        self.assertEqual(m.memory[0xC100], 0x91)
        self.assertFalse(m._cpu_bus_active)

    def test_HRAM_CPU_can_read_and_write_HRAM_during_DMA(self):
        m = make_machine()
        m.pc = 0xFF80
        m.memory[0xFF80:0xFF84] = bytes((0x7E, 0x77, 0x00, 0x00))
        m._set_pair(2, 0xFF90)
        m.memory[0xFF90] = 0xA2
        m.write(0xFF46, 0xC0)
        m.instruction()
        self.assertEqual(m.a, 0xA2)
        m.a = 0xB5
        m.instruction()
        self.assertEqual(m.memory[0xFF90], 0xB5)

    def test_ROM_opcode_fetch_during_DMA_fails_closed_not_fake_training(self):
        m = make_machine()
        m.write(0xFF46, 0xC0)
        original_pc = m.pc
        with self.assertRaisesRegex(GameRomRuntimeError, "outside HRAM"):
            m.instruction()
        self.assertEqual(m.pc, original_pc)
        self.assertFalse(m._cpu_bus_active)

    def test_DMA_IRQ_bus_phase_fails_closed(self):
        m = make_machine()
        m.pc = 0xFF80
        m.memory[0xFF80] = 0
        m.write(0xFF46, 0xC0)
        m.memory[0xFFFF] = 1
        m.memory[0xFF0F] = 1
        m.ime = True
        with self.assertRaisesRegex(GameRomRuntimeError, "IRQ service"):
            m.instruction()
        self.assertFalse(m._cpu_bus_active)

    def test_invalid_HRAM_opcode_does_not_leave_CPU_bus_context_attached(self):
        m = make_machine()
        m.pc = 0xFF80
        m.memory[0xFF80] = 0xD3  # Invalid SM83 opcode.
        m.write(0xFF46, 0xC0)
        with self.assertRaises(GameRomRuntimeError):
            m.instruction()
        self.assertFalse(m._cpu_bus_active)
        self.assertEqual(m.read(0xC000), 0x80)

    def test_CPU_video_bus_reads_are_denied_only_during_relevant_PPU_modes(self):
        for address, cases in (
            (0x8000, ((0, 0x6B), (99, 0xFF), (270, 0x6B))),
            (0xFE00, ((0, 0xFF), (99, 0xFF), (270, 0x6B))),
        ):
            with self.subTest(address=address):
                for cycle, expected in cases:
                    m = make_machine()
                    m.pc = 0x100
                    # LD A,(HL); source test ROM has a controlled
                    # original cartridge instruction in bank zero.
                    cart = bytearray(m.rom)
                    cart[0x100] = 0x7E
                    m = GameBoyMachine(bytes(cart))
                    m.memory[address] = 0x6B
                    m._set_pair(2, address)
                    m.line_cycles = cycle
                    m.memory[0xFF44] = 0
                    m.instruction()
                    self.assertEqual(m.a, expected)

    def test_CPU_video_bus_writes_respect_mode_and_LCDC_disable(self):
        for address, blocked_cycle in ((0x8000, 90), (0xFE00, 20)):
            with self.subTest(address=address):
                rom = bytearray(synthetic_rom(0x00, 0, 0))
                rom[0x100] = 0x77  # LD (HL),A
                m = GameBoyMachine(bytes(rom))
                m._set_pair(2, address)
                m.a = 0xB3
                m.memory[address] = 0x72
                m.line_cycles = blocked_cycle
                m.instruction()
                self.assertEqual(m.memory[address], 0x72)
                m.pc = 0x100
                m.memory[0xFF40] &= ~0x80  # LCDC off: no video bus contention.
                m.instruction()
                self.assertEqual(m.memory[address], 0xB3)

    def test_PPU_and_DMA_internal_memory_views_ignore_CPU_bus_access_flags(self):
        m = make_machine()
        m.memory[0x8000] = 0x4B
        m.memory[0xFE00] = 0xB2
        m.line_cycles = 100
        self.assertEqual(m.read(0x8000), 0x4B)
        self.assertEqual(m.read(0xFE00), 0xB2)
        m.write(0xFF46, 0xC0)
        m._advance(8)
        self.assertEqual(m.memory[0xFE00], 0x80)
        self.assertFalse(m._cpu_bus_active)

    def test_reject_unsupported_page_and_tampered_inflight_state(self):
        m = make_machine()
        with self.assertRaises(GameRomRuntimeError):
            m.write(0xFF46, 0xF0)
        with self.assertRaises(GameRomRuntimeError):
            m.write(0xFF46, 0xFF)
        m.write(0xFF46, 0xC0)
        initial = m.snapshot()
        for field, value in (
            ("dma_source", 0xC001),
            ("dma_index", 160),
            ("dma_tcycles", 4),
            ("dma_startup", 5),
        ):
            with self.subTest(field=field):
                malformed = json.loads(json.dumps(initial))
                malformed["registers"][field] = value
                with self.assertRaises(GameRomRuntimeError):
                    m.restore(resign(malformed))


if __name__ == "__main__":
    unittest.main()
