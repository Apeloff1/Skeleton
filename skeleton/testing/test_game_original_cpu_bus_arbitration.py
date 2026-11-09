"""Executable original DMG video/DMA CPU bus and acceptance custody tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_original_gameboy_bus_arbitration import (
    OriginalBusError,
    audit_original_bus_arbitration,
)
from scripts.run_game_rom_acceptance_suite import (
    AcceptanceSuiteError, _canonical, _sha, _verify_cpu_bus_arbitration,
)
from skeleton.jeeves.game_rom_runtime import GameBoyMachine
from scripts.audit_original_gameboy_cpu_opcodes import _cartridge


class OriginalCPUAndVideoBusProofs(unittest.TestCase):
    def test_actual_CPU_PPU_DMA_arbitration_has_all_source_proofs(self):
        report = audit_original_bus_arbitration()
        self.assertEqual(report["actual_CPU_memory_and_DMA_reference_checks"], 21)
        self.assertEqual(len(report["tested_source_bus_constraints"]), 21)
        self.assertTrue(report["cpu_dma_hram_only"])
        self.assertTrue(report["cpu_video_ppu_mode_lockout"])
        self.assertTrue(report["exact_inflight_DMA_savestate_replay"])
        self.assertFalse(report["source_video_timing_dot_perfect"])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "original-cpu-bus.json"
            path.write_bytes(_canonical(report) + b"\n")
            passed = _verify_cpu_bus_arbitration(Path(d))
            self.assertTrue(passed["accepted"])
            self.assertEqual(passed["original_cpu_bus_checks"], 21)

    def test_rehashed_missing_HRAM_proof_is_rejected(self):
        report = audit_original_bus_arbitration()
        report["tested_source_bus_constraints"].remove(
            "active_DMA_CPU_HRAM_read_allowed"
        )
        report["actual_CPU_memory_and_DMA_reference_checks"] = 20
        report["report_digest"] = _sha(_canonical({
            k: v for k, v in report.items() if k != "report_digest"
        }))
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "original-cpu-bus.json").write_bytes(
                _canonical(report) + b"\n"
            )
            with self.assertRaises(AcceptanceSuiteError):
                _verify_cpu_bus_arbitration(Path(d))

    def test_dropped_HRAM_write_cannot_pass_original_source_bus_audit(self):
        original_write = GameBoyMachine.write

        def invalid_write(core, address, value):
            if core._cpu_bus_active and (address & 0xFFFF) == 0xFF90:
                return
            return original_write(core, address, value)

        with patch.object(GameBoyMachine, "write", invalid_write):
            with self.assertRaises(OriginalBusError):
                audit_original_bus_arbitration()

    def test_CPU_bus_context_is_cleared_after_decode_errors(self):
        machine = GameBoyMachine(_cartridge(0xD3))
        with self.assertRaises(Exception):
            machine.instruction()
        self.assertFalse(machine._cpu_bus_active)
        self.assertEqual(machine.pc, 0x101)

    def test_opaque_snapshot_does_not_claim_CPU_bus_owner_as_persistent(self):
        machine = GameBoyMachine(_cartridge(0))
        source = machine.snapshot()
        self.assertNotIn("_cpu_bus_active", source["registers"])
        machine._cpu_bus_active = True
        machine._cpu_bus_active = False
        machine.restore(source)
        self.assertFalse(machine._cpu_bus_active)


if __name__ == "__main__":
    unittest.main()
