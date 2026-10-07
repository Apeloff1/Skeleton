from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FunctionalLLMGameBuilderExecutionBacklogTest(unittest.TestCase):
    def test_execution_backlog_validator_passes(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_functional_llm_game_builder_execution_backlog.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
        self.assertIn("216 build units", proc.stdout)


    def test_frontier_competition_is_bound_to_whole_product_closure(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        gate = backlog["frontier_competition_gate"]
        self.assertFalse(gate["completion_claim"])
        self.assertEqual(gate["required_task_ids"], ["FLGB-18-T11", "FLGB-18-T12"])
        self.assertEqual(len(gate["core_targets"]), 3)
        self.assertGreaterEqual(len(gate["required_outputs"]), 17)
        self.assertEqual(gate["protocol_version"], "2.0")
        measurement = gate["measurement_requirements"]
        self.assertLessEqual(measurement["comparator_maximum_age_days"], 45)
        self.assertGreaterEqual(measurement["minimum_independent_runs_per_scored_task"], 6)
        self.assertGreaterEqual(measurement["confidence_interval_level"], 0.95)
        self.assertLessEqual(measurement["non_inferiority_margin_pp_max"], 2.0)
        self.assertGreaterEqual(measurement["minimum_parity_or_better_domains"], 10)
        self.assertGreaterEqual(measurement["minimum_superior_core_targets"], 2)
        self.assertTrue(measurement["equal_budget_head_to_head"])
        self.assertTrue(measurement["compute_normalized_pareto"])
        self.assertTrue(measurement["hidden_challenge_rotation"])
        self.assertTrue(measurement["anti_gaming_review"])
        self.assertTrue(measurement["long_horizon_50_and_80_percent_curves"])
        self.assertTrue(measurement["evaluator_independence"])
        by_id = {task["id"]: task for task in backlog["tasks"]}
        for task_id in gate["required_task_ids"]:
            task = by_id[task_id]
            corpus = " ".join(task["acceptance_gates"])
            self.assertIn("12-domain frontier competition scorecard", corpus)
            self.assertIn("frontier parity-or-better", corpus)
            self.assertIn("blind human evaluation", corpus)
            closure = task["closure_rule"].lower()
            self.assertIn("frontier protocol v2", closure)
            self.assertIn("six independent", closure)
            self.assertIn("50%/80%", closure)
            self.assertIn("compute-normalized", closure)
            self.assertIn("anti-gaming", closure)
            self.assertIn("evaluator independence", closure)
            self.assertIn("statistical dominance", closure)


    def test_plane_01_implementation_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-01")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])

        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-01"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertFalse(task["implementation_signed"])
            self.assertFalse(task["independent_verification_signed"])
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_02_model_runtime_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-02")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-02"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_03_context_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-03")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-03"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_04_agent_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-04")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-04"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_05_security_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-05")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-05"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_06_assurance_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-06")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-06"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_07_training_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-07")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-07"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_08_multimodal_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-08")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-08"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_09_game_editor_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-09")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-09"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_10_simulation_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-10")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-10"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


    def test_plane_11_rendering_inventory_is_present_but_unsigned(self) -> None:
        backlog = json.loads(
            (ROOT / "machine/functional_llm_game_builder_execution_backlog.json").read_text(
                encoding="utf-8"
            )
        )
        plane = next(item for item in backlog["planes"] if item["id"] == "FLGB-11")
        self.assertEqual(plane["state"], "implemented-pending-verification")
        self.assertFalse(plane["implementation_signed"])
        self.assertFalse(plane["independent_verification_signed"])
        tasks = [item for item in backlog["tasks"] if item["plane_id"] == "FLGB-11"]
        self.assertEqual(len(tasks), 12)
        for task in tasks:
            self.assertEqual(task["state"], "implemented-pending-verification")
            self.assertTrue((ROOT / task["implementation_target"]).is_file())
            self.assertTrue((ROOT / task["contract_target"]).is_file())
            self.assertTrue((ROOT / task["test_target"]).is_file())


if __name__ == "__main__":
    unittest.main()
