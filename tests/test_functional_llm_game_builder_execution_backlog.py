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
        self.assertGreaterEqual(len(gate["required_outputs"]), 10)
        by_id = {task["id"]: task for task in backlog["tasks"]}
        for task_id in gate["required_task_ids"]:
            task = by_id[task_id]
            corpus = " ".join(task["acceptance_gates"])
            self.assertIn("12-domain frontier competition scorecard", corpus)
            self.assertIn("frontier parity-or-better", corpus)
            self.assertIn("blind human evaluation", corpus)
            self.assertIn("frontier-competition gate", task["closure_rule"])


if __name__ == "__main__":
    unittest.main()
