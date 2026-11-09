"""Real original ROM serial execution custody and acceptance refusals."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.audit_original_gameboy_serial_port import (
    _run, audit_serial_port,
)
from scripts.run_game_rom_acceptance_suite import (
    _canonical, _sha, _verify_serial_source, AcceptanceSuiteError,
)


class OwnedROMSerialLinkEvidenceTests(unittest.TestCase):
    def test_real_source_rom_initializes_serial_and_completes_internal_clock(self):
        row = _run(0x81)
        self.assertEqual(row["CPU_started_actual_SB_SC_writes"], 4)
        self.assertEqual(row["actual_cpu_clock_advance_instructions"], 1021)
        self.assertEqual(row["source_program_cpu_instruction_calls"], 1025)
        self.assertEqual(row["serial_start_opcode_clocked_tcycles"], 12)
        self.assertEqual(row["actual_source_SB_SC_program_tcycles"], 40)
        self.assertEqual(row["real_serial_phase_just_after_SC_opcode"], 12)
        self.assertEqual(row["serial_final_SB"], 255)
        self.assertTrue(row["serial_interrupt_set"])
        self.assertFalse(row["serial_SC_still_active"])
        self.assertEqual(row["source_finished_snapshot_sha256"],
                         row["source_replayed_snapshot_sha256"])

    def test_external_clock_without_peer_does_not_invent_completion(self):
        row = _run(0x80)
        self.assertEqual(row["serial_final_SB"], 0x6A)
        self.assertFalse(row["serial_interrupt_set"])
        self.assertTrue(row["serial_SC_still_active"])
        self.assertEqual(row["real_serial_phase_just_after_SC_opcode"], 0)
        self.assertEqual(row["actual_source_SB_SC_program_tcycles"], 40)

    def test_both_real_source_runs_produce_admissible_report(self):
        result = audit_serial_port()
        self.assertEqual(result["real_serial_cpu_modes"], 2)
        self.assertEqual(result["actual_cpu_oscillator_steps"], 2042)
        self.assertEqual(result["actual_original_cpu_instruction_calls"], 2050)
        self.assertFalse(result["interconsole_link_gameplay_verified"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original-serial-clock.json"
            path.write_bytes(_canonical(result) + b"\n")
            self.assertTrue(_verify_serial_source(Path(directory))["accepted"])

    def test_rehashed_fake_multiplayer_and_no_interrupt_fail_closed(self):
        for tamper in ("fake_multiplayer", "lost_interrupt"):
            result = audit_serial_port()
            if tamper == "fake_multiplayer":
                result["interconsole_link_gameplay_verified"] = True
            else:
                result["real_source_trials"][0]["serial_interrupt_set"] = False
            result["report_digest"] = _sha(_canonical({
                k: v for k, v in result.items() if k != "report_digest"
            }))
            with tempfile.TemporaryDirectory() as directory:
                (Path(directory) / "original-serial-clock.json").write_bytes(
                    _canonical(result) + b"\n"
                )
                with self.assertRaises(AcceptanceSuiteError):
                    _verify_serial_source(Path(directory))


if __name__ == "__main__":
    unittest.main()
