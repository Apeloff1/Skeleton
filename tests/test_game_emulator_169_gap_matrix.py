"""Contract tests for all 169 canonical emulator-target gap classifications."""
from __future__ import annotations

import unittest

from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry
from skeleton.jeeves.game_emulator_target_gap_matrix import (
    build_emulator_target_gap_matrix,render_emulator_gap_dashboard,
)


class FullTargetCoverageContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Explicit empty registry. No internet, firmware, core library or ROM.
        cls.matrix=build_emulator_target_gap_matrix(registry=GameEmulatorRegistry())

    def test_all_169_targets_are_classified_without_claiming_a_game_boot(self):
        summary=self.matrix["summary"]
        self.assertEqual(summary["canonical_target_count"],169)
        self.assertEqual(len(self.matrix["targets"]),169)
        self.assertEqual(len({x["target_id"] for x in self.matrix["targets"]}),169)
        self.assertEqual(summary["declared_native_core_mapping_targets"],99)
        self.assertEqual(summary["targets_without_native_core_mapping"],70)
        self.assertEqual(summary["installed_approved_core_targets"],0)
        self.assertEqual(summary["real_rom_boot_qualified_in_this_audit"],0)
        self.assertFalse(self.matrix["actual_native_game_qualification_performed"])

    def test_controller_panels_do_not_claim_hardware_fidelity(self):
        summary=self.matrix["summary"]
        self.assertEqual(
            summary["generic_controller_fallback_targets"]+
            summary["named_or_approximate_controller_targets"],169)
        self.assertEqual(summary["generic_controller_fallback_targets"],137)
        self.assertEqual(summary["verified_physical_controller_layouts"],0)
        self.assertTrue(all(not x["actual_native_controller_compatibility_verified"]
                            for x in self.matrix["targets"]))

    def test_no_mapping_does_not_become_a_false_native_core(self):
        rows={row["target_id"]:row for row in self.matrix["targets"]}
        for target in ("ps5","xbox_series","nintendo_switch","ps4","windows_11"):
            self.assertEqual(rows[target]["declared_core_candidate_count"],0)
            self.assertFalse(rows[target]["installed_approved_core_present"])
            self.assertTrue(rows[target]["next_action"])

    def test_self_contained_html_has_filters_and_no_remote_asset_links(self):
        html=render_emulator_gap_dashboard(self.matrix)
        self.assertIn("169-target emulator readiness",html)
        self.assertIn('id="filter"',html)
        self.assertIn('id="search"',html)
        self.assertNotIn("<script src=",html)
        self.assertNotIn("https://",html)


if __name__=="__main__":
    unittest.main()
