"""Original synthetic SM83 interrupt controls, actual execution and audit gates.

Physical source emulation is required; no commercial ROMs, native binaries,
BIOS or production neural model weights are used. Not hardware certification.
"""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_original_gameboy_interrupts import (
    InterruptMatrixError, _machine, _irq_arbitration,
    _ei_delay, _di_after_ei, _halt_bug, _halt_wake, _reti,
    _joypad_wake, audit_interrupt_matrix,
)
from scripts.run_game_rom_acceptance_suite import (
    _canonical, _sha, _verify_interrupt_matrix, AcceptanceSuiteError,
)


class RealSm83InterruptControls(unittest.TestCase):
    def test_all_five_interrupt_priority_vectors_replay_the_same_real_state(self):
        for bit in range(5):
            with self.subTest(bit=bit):
                receipt = _irq_arbitration(bit)
                self.assertTrue(receipt["real_interrupt_replay_passed"])
                self.assertEqual(receipt["actual_execution_cycles"], 20)
                self.assertEqual(
                    receipt["actual_source_after_sha256"],
                    receipt["replayed_source_after_sha256"],
                )

    def test_ime_delay_di_halt_bug_reti_and_joypad_wake_replay(self):
        actions = (
            _ei_delay, _di_after_ei, _halt_bug,
            _halt_wake, _reti, _joypad_wake,
        )
        for action in actions:
            with self.subTest(name=action.__name__):
                outcome = action()
                self.assertTrue(outcome["real_interrupt_replay_passed"])
                self.assertFalse(outcome["hardware_bus_cycle_certified"])

    def test_original_source_halt_bug_reuses_next_instruction_opcode_as_immediate(self):
        # If HALT bug is implemented as a normal HALT, this exact source
        # position should fail; it instead executes LD A, 3E from the same
        # duplicated byte 3E.
        m = _machine(bytes((0x76, 0x3E, 0x42)))
        m.memory[0xFFFF] = 1
        m.memory[0xFF0F] = 1
        m.instruction()
        self.assertTrue(m.halt_bug)
        m.instruction()
        self.assertEqual(m.a, 0x3E)
        self.assertEqual(m.pc, 0x102)

    def test_missing_and_modified_source_irq_scenarios_fail_even_rehashed(self):
        report = audit_interrupt_matrix()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "original-interrupt-control.json"
            out.write_bytes(_canonical(report) + b"\n")
            verified = _verify_interrupt_matrix(Path(folder))
            self.assertEqual(verified["real_interrupt_scenarios"], 11)
            forged = copy.deepcopy(report)
            forged["source_scenarios"][1]["probe"] = "priority_vector_0"
            forged["report_digest"] = _sha(_canonical({
                key: value for key, value in forged.items() if key != "report_digest"
            }))
            out.write_bytes(_canonical(forged) + b"\n")
            with self.assertRaises(AcceptanceSuiteError):
                _verify_interrupt_matrix(Path(folder))
            forged = copy.deepcopy(report)
            forged["source_scenarios"].pop()
            forged["report_digest"] = _sha(_canonical({
                key: value for key, value in forged.items() if key != "report_digest"
            }))
            out.write_bytes(_canonical(forged) + b"\n")
            with self.assertRaises(AcceptanceSuiteError):
                _verify_interrupt_matrix(Path(folder))

    def test_reference_guard_detects_wrong_interruption_vector(self):
        from skeleton.jeeves.game_rom_runtime import GameBoyMachine

        original = GameBoyMachine.instruction

        def broken(core):
            value = original(core)
            if core.pc == 0x40:
                core.pc = 0x48
            return value

        with patch.object(GameBoyMachine, "instruction", broken):
            with self.assertRaises(InterruptMatrixError):
                _irq_arbitration(0)


if __name__ == "__main__":
    unittest.main()
