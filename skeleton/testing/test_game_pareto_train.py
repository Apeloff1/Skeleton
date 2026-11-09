"""Focused local contract checks for the bounded game Pareto operator.

No model downloads, provider credentials, training jobs, or CI workflow changes.
"""

from __future__ import annotations

import argparse
import math
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from skeleton.ai.runtime.inference import game_pareto_train as subject


class GameParetoPlanTests(unittest.TestCase):
    def test_exact_exposure_distribution(self) -> None:
        receipt, documents, heldout = subject.plan()
        self.assertEqual(receipt["distinct_training_cases"], 40)
        self.assertEqual(receipt["distinct_core_cases"], 8)
        self.assertEqual(receipt["heldout_cases"], 16)
        self.assertEqual(receipt["scheduled_exposures"], 160)
        self.assertEqual(receipt["core_exposures"], 128)
        self.assertEqual(receipt["tail_exposures"], 32)
        self.assertEqual(len(documents), 160)
        self.assertEqual(len(heldout), 16)
        self.assertEqual(
            receipt["family_exposures"],
            {
                "mechanics": 32,
                "narrative": 32,
                "npc": 24,
                "world": 24,
                "economy": 16,
                "tooling": 16,
                "accessibility": 8,
                "review": 8,
            },
        )
        self.assertFalse(set(heldout).intersection(documents))
        for offset in range(0, len(documents), 5):
            group = documents[offset : offset + 5]
            self.assertEqual(len(group), 5)
            self.assertEqual(sum(case in self._cores() for case in group), 4)

    @staticmethod
    def _cores() -> set[str]:
        return {
            max(
                group["train"],
                key=lambda row: (subject._priority(row), row[4]),
            )[4]
            for group in subject.CURRICULUM.values()
        }

    def test_repeatable_curriculum_and_receipts(self) -> None:
        self.assertEqual(subject.plan(), subject.plan())
        first, documents, holdout = subject.plan()
        self.assertEqual(first["train_schedule_digest"], subject._digest(documents))
        self.assertEqual(first["heldout_digest"], subject._digest(holdout))

    def test_reject_uneven_family_shares(self) -> None:
        curriculum = {
            name: dict(group) for name, group in subject.CURRICULUM.items()
        }
        curriculum["mechanics"]["share"] = 21
        with patch.object(subject, "CURRICULUM", curriculum):
            with self.assertRaisesRegex(ValueError, "100"):
                subject.plan()

    def test_reject_train_heldout_contamination(self) -> None:
        curriculum = {
            name: dict(group) for name, group in subject.CURRICULUM.items()
        }
        curriculum["review"]["holdout"] = [
            curriculum["review"]["train"][0][4],
            curriculum["review"]["holdout"][1],
        ]
        with patch.object(subject, "CURRICULUM", curriculum):
            with self.assertRaisesRegex(ValueError, "contamination"):
                subject.plan()

    def test_gating_numbers_are_finite(self) -> None:
        for invalid in (float("nan"), math.inf, -0.01, True, "0.1"):
            with self.assertRaises(ValueError):
                subject._valid_number(invalid, "bound", upper=1)


class GameParetoInputTests(unittest.TestCase):
    def test_no_output_can_replace_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "parent.json"
            path.write_text("{}", encoding="utf-8")
            options = argparse.Namespace(
                output=path,
                base_artifact=path,
                bootstrap=False,
                epochs=1,
                learning_rate=0.005,
                max_family_regression=0.1,
                max_retention_regression=0.05,
                min_relative_gain=0.0,
                retention_corpus=[],
                hidden_size=32,
                model_id="unused",
                seed=0,
            )
            with self.assertRaisesRegex(ValueError, "existing candidate"):
                subject.train(options)
            self.assertEqual(path.read_text(encoding="utf-8"), "{}")

    def test_exclusive_candidate_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            protected = directory / "protected.json"
            protected.write_text("existing", encoding="utf-8")

            def writer(_model, destination):
                destination.write_text("new candidate", encoding="utf-8")
                return "receipt"

            with self.assertRaises(FileExistsError):
                subject._publish_new_candidate(object(), protected, writer)
            self.assertEqual(protected.read_text(encoding="utf-8"), "existing")

            fresh = directory / "fresh.json"
            receipt = subject._publish_new_candidate(object(), fresh, writer)
            self.assertEqual(receipt, "receipt")
            self.assertEqual(fresh.read_text(encoding="utf-8"), "new candidate")

    def test_reject_retention_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "source.txt"
            link = Path(temp) / "link.txt"
            data.write_text("a tiny original sentence", encoding="utf-8")
            try:
                link.symlink_to(data)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not available")
            with self.assertRaisesRegex(ValueError, "symlink"):
                subject._retention_documents([link])


if __name__ == "__main__":
    unittest.main()
