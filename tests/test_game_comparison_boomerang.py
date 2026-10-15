"""Finite boomerang game-study scheduler and no-ROM operator contracts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skeleton.jeeves.game_comparison_boomerang import (
    plan_comparison_boomerang,verify_boomerang_plan,
    make_boomerang_progress,
)
from skeleton.jeeves.game_comparison_counterfactual import ComparativeExperimentError
from tests.test_game_comparison_counterfactual import study
from scripts.run_game_comparison_boomerang import main


class BoomerangCurriculumPlanningContracts(unittest.TestCase):
    def plan(self,**kwargs):
        return plan_comparison_boomerang(
            study(),game_ids=["test_one","test_two"],**kwargs,
        )

    def test_revisit_queue_is_deterministic_and_bounded(self):
        plan=self.plan(treatments=3,revisit_rounds=2,repeats=2)
        self.assertEqual(plan,verify_boomerang_plan(plan,study()))
        self.assertEqual(plan,self.plan(treatments=3,revisit_rounds=2,repeats=2))
        self.assertEqual(plan["estimated_fresh_native_worker_runs"],72)
        self.assertEqual(len(plan["schedule"]),9)
        self.assertEqual(
            sorted({task["phase"] for task in plan["schedule"]}),
            ["after","earlier","middle"],
        )
        for treatment in plan["treatments"]:
            self.assertTrue(all(
                baseline!=treatment["replacement_action"]
                for baseline in treatment["baseline_action_by_game"].values()
            ))
        self.assertFalse(plan["actual_emulation_performed"])
        self.assertEqual(plan["actual_ai_parameter_updates"],0)

    def test_invalid_cost_and_missing_rights_block_planning(self):
        with self.assertRaises(ComparativeExperimentError):
            self.plan(treatments=8)
        with self.assertRaises(ComparativeExperimentError):
            self.plan(treatments=3,revisit_rounds=3)
        m=study()
        m["games"][0]["rights_evidence_digest"]=None
        with self.assertRaises(ComparativeExperimentError):
            plan_comparison_boomerang(
                m,game_ids=["test_one","test_two"],treatments=2,
            )

    def test_tampered_schedule_rejected_even_with_rehashed_root(self):
        plan=self.plan()
        plan["schedule"][0]["replacement_action"]="y"
        from skeleton.jeeves.game_comparison_schema import digest
        plan["plan_sha256"]=digest({
            key:value for key,value in plan.items() if key!="plan_sha256"
        })
        with self.assertRaises(ComparativeExperimentError):
            verify_boomerang_plan(plan,study())

    def test_empty_progress_is_pending_not_success(self):
        plan=self.plan()
        report=make_boomerang_progress(plan,[])
        self.assertEqual(report["status"],"partial_with_pending_treatments")
        self.assertEqual(report["fresh_native_worker_runs_completed"],0)
        self.assertEqual(report["production_model_weights_updated"],0)

    def test_foreign_native_results_not_accepted(self):
        plan=self.plan()
        with self.assertRaises(ComparativeExperimentError):
            make_boomerang_progress(plan,[{"schema_version":"synthetic_forgery"}])

    def test_operator_plan_only_does_not_run_rom_or_require_core_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            manifest=root/"study.json"
            manifest.write_text(json.dumps(study()))
            out=root/"plan"
            status=main([
                "--manifest",str(manifest),
                "--game","test_one","--game","test_two",
                "--treatments","3","--revisit-rounds","1",
                "--output-dir",str(out),
            ])
            self.assertEqual(status,0)
            plan=json.loads((out/"boomerang_plan.json").read_text())
            report=json.loads((out/"boomerang_progress.json").read_text())
            self.assertEqual(plan["estimated_fresh_native_worker_runs"],48)
            self.assertFalse(plan["actual_emulation_performed"])
            self.assertEqual(report["completed_treatments"],0)
            self.assertEqual(report["status"],"partial_with_pending_treatments")


if __name__=="__main__":
    unittest.main()
