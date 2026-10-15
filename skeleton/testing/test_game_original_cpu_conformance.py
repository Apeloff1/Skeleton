"""Independent original synthetic cartridge LR35902 coverage and flag checks.

No game-ROM downloads. Full manual suite explicitly executes these proofs;
do not treat source code alone as verified hardware certification.
"""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_original_gameboy_alu_flags import (
    _reference, audit_alu_flags, ALUOracleError,
)
from scripts.audit_original_gameboy_cpu_opcodes import (
    INVALID_BASE, _cartridge, _result, audit_cpu_opcode_matrix, OpcodeMatrixError,
)
from scripts.run_game_rom_acceptance_suite import (
    _canonical, _verify_cpu_opcode_matrix, _verify_alu_reference, AcceptanceSuiteError,
)
from skeleton.jeeves.game_rom_runtime import GameBoyMachine


class SourceCPUOpcodeConformanceCases(unittest.TestCase):
    def test_invalid_lr35902_opcode_identity_corpus_has_eleven_elements(self):
        self.assertEqual(len(INVALID_BASE), 11)
        self.assertEqual(sum(op in INVALID_BASE for op in range(256)), 11)
        for opcode in INVALID_BASE:
            row = _result(opcode)
            self.assertTrue(row["expected_invalid_opcode_rejected"])
            self.assertFalse(row["real_instruction_executed"])

    def test_full_legal_CPU_opcodes_replay_from_original_machine_state(self):
        result = audit_cpu_opcode_matrix()
        self.assertEqual(result["actual_total_single_step_source_replays"], 1000)
        self.assertEqual(result["expected_illegal_base_opcodes_rejected"], 11)
        self.assertEqual(len(result["prefixed_instruction_receipts"]), 256)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "original-cpu-opcodes.json"
            target.write_bytes(_canonical(result) + b"\n")
            accepted = _verify_cpu_opcode_matrix(Path(folder))
            self.assertTrue(accepted["accepted"])
            self.assertEqual(accepted["source_cpu_instruction_steps_replayed"], 1000)
            modified = copy.deepcopy(result)
            modified["prefixed_instruction_receipts"][255]["cb"] = 0
            from hashlib import sha256
            modified["report_digest"] = sha256(_canonical({
                k: v for k, v in modified.items() if k != "report_digest"
            })).hexdigest()
            target.write_bytes(_canonical(modified) + b"\n")
            with self.assertRaises(AcceptanceSuiteError):
                _verify_cpu_opcode_matrix(Path(folder))

    def test_cb_bit_operation_on_real_hl_ram_is_not_fake_register_update(self):
        before = _result(0xCB, 0x86)  # RES 0,(HL)
        self.assertEqual(before["emulated_t_cycles"], 16)
        self.assertTrue(before["real_independent_replay_executed"])
        cb_bit = _result(0xCB, 0x46)  # BIT 0,(HL)
        self.assertEqual(cb_bit["emulated_t_cycles"], 12)
        cb_reg = _result(0xCB, 0x07)  # RLC A
        self.assertEqual(cb_reg["emulated_t_cycles"], 8)

    def test_alu_has_independent_5184_boundary_math_comparisons(self):
        report = audit_alu_flags()
        self.assertEqual(report["actual_source_flag_comparisons"], 5184)
        self.assertEqual(report["actual_passed_alu_operations"], 8)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "original-alu-flags.json"
            target.write_bytes(_canonical(report) + b"\n")
            self.assertTrue(_verify_alu_reference(Path(folder))["accepted"])

    def test_reference_catches_source_ALU_mutation_before_AI_training(self):
        with patch.object(GameBoyMachine, "_alu", lambda machine, op, val: None):
            with self.assertRaises(ALUOracleError):
                audit_alu_flags()
        # Explicit borrow boundary, arithmetic half carry and CP A unchanged.
        cp_a, cp_f = _reference(7, 0, 1, 0)
        self.assertEqual(cp_a, 0)
        self.assertNotEqual(cp_f & 0x10, 0)
        self.assertNotEqual(cp_f & 0x20, 0)


if __name__ == "__main__":
    unittest.main()
