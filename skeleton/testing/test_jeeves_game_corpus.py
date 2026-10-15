"""Provenance, integrity and no-leakage contracts for production game datasets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.training.jeeves_game_corpus import (
    FAMILIES, RIGHTS_SCHEMA, SCHEMA, load_approved_corpus,
)
from skeleton.ai.training.jeeves_production_game_train import ProductionCheckpointError


class JeevesGameCorpusTests(unittest.TestCase):
    def _fixtures(self, root: Path):
        families = sorted(FAMILIES)
        def records(split, count):
            rows = []
            for family in families:
                for i in range(count):
                    rows.append({
                        "id": f"{split}_{family}_{i:03d}",
                        "split": split,
                        "family": family,
                        "prompt": f"Design a playable {family} scenario with unique seed {split}-{i} and clear player choices.",
                        "answer": (
                            f"For {family}, use an original coherent game loop with agency, "
                            f"observable feedback and safe recovery. This is the authored "
                            f"{split} case {i}; introduce distinct interactions {family}-{i}."
                        ),
                        "rights": {
                            "schema_version": RIGHTS_SCHEMA,
                            "source_kind": "original_authoring",
                            "rights_holder": "Test fixture author",
                            "rights_basis": "Authored exclusively for local test coverage",
                            "review_id": "fixture-rights-review",
                            "training_permitted": True,
                        },
                    })
            return rows
        train = records("train", 4)
        holdout = records("heldout", 2)
        manifest_path = root / "game-manifest.json"
        def put(name, data):
            raw = b"".join(
                (json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
                for row in data
            )
            (root / name).write_bytes(raw)
            return hashlib.sha256(raw).hexdigest()
        def manifest():
            value = {
                "schema_version": SCHEMA,
                "rights_reviewed": True,
                "review_id": "dataset-legal-review",
                "train_file": "game-train.jsonl",
                "heldout_file": "game-heldout.jsonl",
                "train_sha256": put("game-train.jsonl", train),
                "heldout_sha256": put("game-heldout.jsonl", holdout),
            }
            manifest_path.write_text(json.dumps(value), encoding="utf-8")
            return manifest_path
        return train, holdout, manifest

    def test_valid_approved_corpus_has_eight_separated_domains(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            train, heldout, regenerate = self._fixtures(Path(d))
            path = regenerate()
            examples, evaluations, receipt = load_approved_corpus(path)
            self.assertEqual(len(examples), 32)
            self.assertEqual(sum(map(len, evaluations.values())), 16)
            self.assertEqual(set(evaluations), FAMILIES)
            self.assertEqual(receipt["train_examples"], 32)
            self.assertFalse(receipt["heldout_used_for_training"])
            self.assertTrue(receipt["benchmark_overlap_checked"])

    def test_file_modification_invalidates_admission_sha(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, _, regenerate = self._fixtures(root)
            path = regenerate()
            with (root / "game-train.jsonl").open("ab") as output:
                output.write(b"{}\n")
            with self.assertRaisesRegex(ProductionCheckpointError, "SHA-256"):
                load_approved_corpus(path)

    def test_rights_denial_never_enters_training(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, _, regenerate = self._fixtures(root)
            train[0]["rights"]["training_permitted"] = False
            with self.assertRaisesRegex(ProductionCheckpointError, "not permitted"):
                load_approved_corpus(regenerate())

    def test_scraped_or_unknown_rights_never_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, _, regenerate = self._fixtures(root)
            train[0]["rights"]["source_kind"] = "unverified_scrape"
            with self.assertRaisesRegex(ProductionCheckpointError, "unapproved source"):
                load_approved_corpus(regenerate())

    def test_heldout_prompt_copy_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, heldout, regenerate = self._fixtures(root)
            heldout[0]["prompt"] = train[0]["prompt"]
            with self.assertRaisesRegex(ProductionCheckpointError, "prompt leaked"):
                load_approved_corpus(regenerate())

    def test_heldout_reference_copy_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, heldout, regenerate = self._fixtures(root)
            heldout[0]["answer"] = train[0]["answer"]
            with self.assertRaisesRegex(ProductionCheckpointError, "answer copied"):
                load_approved_corpus(regenerate())

    def test_near_duplicate_heldout_reference_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, heldout, regenerate = self._fixtures(root)
            # Preserve the main reference text and only modify one final
            # word. A high lexical score here would measure copying, not
            # game-design generalization.
            heldout[0]["answer"] = train[0]["answer"] + " extra"
            with self.assertRaisesRegex(ProductionCheckpointError, "near-duplicates"):
                load_approved_corpus(regenerate())

    def test_immutable_benchmark_prompt_cannot_enter_training(self) -> None:
        from skeleton.ai.training.jeeves_game_design_benchmark import BENCHMARK
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, _, regenerate = self._fixtures(root)
            train[0]["prompt"] = BENCHMARK[0][1]
            with self.assertRaisesRegex(ProductionCheckpointError, "benchmark"):
                load_approved_corpus(regenerate())

    def test_cross_split_record_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, heldout, regenerate = self._fixtures(root)
            heldout[0]["id"] = train[0]["id"]
            with self.assertRaisesRegex(ProductionCheckpointError, "duplicate record ID"):
                load_approved_corpus(regenerate())

    def test_missing_family_quota_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, _, regenerate = self._fixtures(root)
            train[:] = [row for row in train if row["family"] != "npc"]
            with self.assertRaisesRegex(ProductionCheckpointError, "each game family"):
                load_approved_corpus(regenerate())

    def test_path_traversal_blocked_before_reading_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, _, regenerate = self._fixtures(root)
            path = regenerate()
            data = json.loads(path.read_text())
            data["train_file"] = "../../stolen.jsonl"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ProductionCheckpointError, "basename"):
                load_approved_corpus(path)


if __name__ == "__main__":
    unittest.main()
