"""Offline comparison readiness doctor: temporary original ROM fixtures only."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from skeleton.jeeves.game_comparison_readiness import inspect_game_comparison_readiness
from skeleton.jeeves.game_comparison_schema import digest


def game(identity,path,order):
    return {
        "id":identity,"title":identity,
        "series_id":"unit_test_only","release_order":order,
        "release_year":2026,"series_phase":"earlier" if order==1 else "middle",
        "target_id":"nes","core_id":"fceumm",
        "source_path":str(path),
        "source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "rights_evidence_digest":None,
        "actions":["idle","right","a"],
        "seed":1,"frames_per_step":1,"controller_devices":["joypad"],
    }


class OfflineReadinessContracts(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        base=Path(self.folder.name)
        files=[base/"alpha.nes",base/"beta.nes"]
        files[0].write_bytes(b"synthetic-not-a-game-a")
        files[1].write_bytes(b"synthetic-not-a-game-b")
        self.model={
            "schema_version":"skeleton.game.comparative_study.v1",
            "study_id":"synthetic_readiness_only",
            "title":"No native execution",
            "max_active":2,
            "games":[game("alpha",files[0],1),game("beta",files[1],2)],
            "pairs":[{"left_id":"alpha","right_id":"beta","questions":[]}],
            "notes":[],
        }
        self.registry=SimpleNamespace(
            registry_digest=digest(["unit_test_approved_registry"]),
            resolve_core=lambda core:SimpleNamespace(target_ids=("nes",)),
        )

    def test_all_sources_and_disk_verified_without_native_execution(self):
        report=inspect_game_comparison_readiness(
            self.model,registry=self.registry,free_temp_bytes=16*1024**3,
        )
        self.assertEqual(report["game_preflight_pass_count"],2)
        self.assertFalse(report["native_emulation_executed_by_doctor"])
        self.assertFalse(report["runtime_correctness_guaranteed"])
        self.assertTrue(report["cohorts"][0]["supports_simultaneous_live_desk_without_reduction"])
        self.assertTrue(report["games"]["alpha"]["source"]["all_file_hashes_verified"])
        self.assertIn("source_rights_record_missing_for_opt_in_learning",
                      report["games"]["alpha"]["blockers"])

    def test_changed_content_produces_explicit_blocker(self):
        gamefile=Path(self.model["games"][0]["source_path"])
        gamefile.write_bytes(b"tampered")
        report=inspect_game_comparison_readiness(
            self.model,registry=self.registry,free_temp_bytes=16*1024**3,
        )
        self.assertEqual(report["game_preflight_pass_count"],1)
        self.assertFalse(report["games"]["alpha"]["source_and_registry_preflight_passed"])
        self.assertTrue(any(x.startswith("source:") for x in report["games"]["alpha"]["blockers"]))

    def test_missing_core_not_faked_as_approved(self):
        def absent(_):
            raise ValueError("not installed")
        self.registry.resolve_core=absent
        report=inspect_game_comparison_readiness(
            self.model,registry=self.registry,free_temp_bytes=16*1024**3,
        )
        self.assertEqual(report["game_preflight_pass_count"],0)
        self.assertEqual(report["core_input_hardware_qualified_count"],0)

    def test_good_source_not_reported_live_ready_when_host_cannot_sandbox(self):
        from unittest.mock import patch
        blocked={
            "native_launch_preflight_passed":False,
            "blockers":[{"code":"bubblewrap_missing","severity":"blocker"}],
            "sandbox_probe":{"requested":False,"passed":False},
        }
        with patch("skeleton.jeeves.game_comparison_host_preflight.inspect_native_host_runtime",
                   return_value=blocked):
            report=inspect_game_comparison_readiness(
                self.model,registry=self.registry,free_temp_bytes=16*1024**3,
            )
        self.assertEqual(report["game_preflight_pass_count"],2)
        self.assertFalse(report["ready_for_all_live_study_cohorts"])
        self.assertFalse(report["cohorts"][0]["ready_for_simultaneous_live_desk"])
        self.assertEqual(report["host_runtime"]["blockers"][0]["code"],"bubblewrap_missing")

    def test_disk_budget_rejects_full_batch(self):
        report=inspect_game_comparison_readiness(
            self.model,registry=self.registry,free_temp_bytes=128,
        )
        self.assertIsNotNone(report["cohorts"][0]["disk_issue"])
        self.assertFalse(report["cohorts"][0]["supports_simultaneous_live_desk_without_reduction"])


if __name__=="__main__":
    unittest.main()
