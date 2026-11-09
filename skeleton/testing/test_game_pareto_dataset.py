"""Offline checks for chat-SFT export without any model training."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from skeleton.ai.runtime.inference.game_pareto_dataset import _pair, export


class GameParetoDatasetTests(unittest.TestCase):
    def test_parse_strict_authored_pair(self) -> None:
        row = _pair("User: Make a quest. Jeeves: Specify goals and rewards.")
        self.assertEqual(row["messages"][0]["role"], "user")
        self.assertEqual(row["messages"][0]["content"], "Make a quest.")
        self.assertEqual(row["messages"][1]["role"], "assistant")
        self.assertEqual(row["messages"][1]["content"], "Specify goals and rewards.")
        for invalid in (
            "Player: Choose a path. Jeeves: Make it fair.",
            "User: Missing assistant.",
            "User:  Jeeves: Answer.",
            "User: Prompt Jeeves: ",
        ):
            with self.assertRaises(ValueError):
                _pair(invalid)

    def test_export_is_deterministic_and_disjoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            train = root / "train.jsonl"
            evaluation = root / "holdout.jsonl"
            manifest = root / "manifest.json"
            report = export(train, evaluation, manifest)
            training_bytes = train.read_bytes()
            evaluation_bytes = evaluation.read_bytes()
            saved = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(report["training_sft_records"], 160)
            self.assertEqual(report["evaluation_records"], 16)
            self.assertEqual(
                saved["training_sha256"], hashlib.sha256(training_bytes).hexdigest()
            )
            self.assertEqual(
                saved["evaluation_sha256"], hashlib.sha256(evaluation_bytes).hexdigest()
            )
            train_lines = [json.loads(line) for line in training_bytes.splitlines()]
            eval_lines = [json.loads(line) for line in evaluation_bytes.splitlines()]
            self.assertEqual(len(train_lines), 160)
            self.assertEqual(len(eval_lines), 16)
            self.assertFalse(
                {json.dumps(row, sort_keys=True) for row in train_lines}
                .intersection(json.dumps(row, sort_keys=True) for row in eval_lines)
            )
            self.assertTrue(saved["heldout_excluded_from_training"])
            self.assertFalse(saved["external_training_executed"])
            self.assertFalse(saved["production_promotion"])
            with self.assertRaisesRegex(ValueError, "overwrite"):
                export(train, evaluation, manifest)
            self.assertEqual(train.read_bytes(), training_bytes)

    def test_reject_overlapping_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            one = root / "same.jsonl"
            with self.assertRaisesRegex(ValueError, "separate"):
                export(one, one, root / "manifest.json")


if __name__ == "__main__":
    unittest.main()
