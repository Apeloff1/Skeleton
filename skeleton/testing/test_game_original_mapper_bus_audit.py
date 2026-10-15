"""Source-only mapper bus matrix regressions with no copyrighted ROM data."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_original_gameboy_mapper_matrix import (
    MapperAuditError, _CASES, _probe, _rom, audit_mapper_matrix,
)
from scripts.run_game_rom_acceptance_suite import (
    AcceptanceSuiteError, _canonical, _sha, _verify_mapper_bus,
)
from skeleton.jeeves.game_rom_runtime import (
    GameRomRuntimeError, inspect_dmg_cartridge,
)


class ActualInterpreterMapperMatrixTests(unittest.TestCase):
    def test_five_source_rom_mapper_types_with_exact_bank_and_ram_checks(self):
        report = audit_mapper_matrix()
        self.assertEqual(report["tested_actual_mapper_categories"], 5)
        self.assertGreater(report["verified_source_bus_checks"], 20)
        self.assertTrue(all(
            proof["actual_memory_cpu_savestate_roundtrip"]
            for proof in report["mapper_results"]
        ))
        self.assertEqual(
            report["mapped_cartridge_categories"],
            ["rom_only", "mbc1", "mbc2", "mbc3", "mbc5"],
        )
        self.assertEqual(report["production_model_weights_updated"], 0)
        self.assertFalse(report["native_libretro_hardware_certified"])

    def test_each_self_authored_cartridge_has_a_valid_source_checksum(self):
        for label, cartridge, rom_size, ram_size in _CASES:
            with self.subTest(mapper=label):
                rom = _rom(cartridge, rom_size, ram_size)
                metadata = inspect_dmg_cartridge(rom)
                self.assertEqual(metadata["mapper"], label)
                self.assertEqual(metadata["rom_bytes"], len(rom))

    def test_source_diagnostic_refuses_corrupt_or_foreign_bus(self):
        with patch(
            "scripts.audit_original_gameboy_mapper_matrix.GameBoyMachine",
        ) as mocked:
            mocked.return_value.metadata = {"rom_digest": "0" * 64, "mapper": "rom_only"}
            with self.assertRaises(MapperAuditError):
                _probe("rom_only", 0, 0, 0)

    def test_acceptance_enforces_per_mapper_exact_receipt_integrity(self):
        report = audit_mapper_matrix()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "original-mapper-bus.json"
            target.write_bytes(_canonical(report) + b"\n")
            verified = _verify_mapper_bus(Path(temp))
            self.assertTrue(verified["accepted"])
            self.assertEqual(verified["real_interpreter_mapper_types"][-1], "mbc5")
            report["mapper_results"][1]["verified_register_and_memory_cases"].pop()
            report["mapper_results"][1]["real_source_bus_checks"] -= 1
            report["mapper_results"][1]["receipt_digest"] = _sha(_canonical({
                key: val for key, val in report["mapper_results"][1].items()
                if key != "receipt_digest"
            }))
            report["verified_source_bus_checks"] -= 1
            report["report_digest"] = _sha(_canonical({
                key: val for key, val in report.items() if key != "report_digest"
            }))
            target.write_bytes(_canonical(report) + b"\n")
            # This remains below the original source number of bus probes
            # only when the altered entry is the now-empty sole proof.
            report["mapper_results"][1]["verified_register_and_memory_cases"] = []
            report["mapper_results"][1]["real_source_bus_checks"] = 0
            report["mapper_results"][1]["receipt_digest"] = _sha(_canonical({
                key: val for key, val in report["mapper_results"][1].items()
                if key != "receipt_digest"
            }))
            report["verified_source_bus_checks"] = sum(
                x["real_source_bus_checks"] for x in report["mapper_results"]
            )
            report["report_digest"] = _sha(_canonical({
                key: val for key, val in report.items() if key != "report_digest"
            }))
            target.write_bytes(_canonical(report) + b"\n")
            with self.assertRaises(AcceptanceSuiteError):
                _verify_mapper_bus(Path(temp))

    def test_no_game_or_hardware_certification_from_rom_only_memory_bus(self):
        details = _probe("rom_only", 0x00, 0, 0)
        self.assertFalse(details["real_native_libretro_core_tested"])
        self.assertFalse(details["commercial_rom_compatibility_certified"])


if __name__ == "__main__":
    unittest.main()
