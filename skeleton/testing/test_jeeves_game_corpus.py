"""Provenance, integrity and no-leakage contracts for production game datasets."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.training.jeeves_game_corpus import (
    FAMILIES, RIGHTS_SCHEMA, SCHEMA, _read_bounded_regular_file, load_approved_corpus,
)
from skeleton.ai.training.jeeves_production_game_train import ProductionCheckpointError


class JeevesGameCorpusTests(unittest.TestCase):
    def _fixtures(self, root: Path):
        families = sorted(FAMILIES)
        def records(split, count):
            rows = []
            for family in families:
                for i in range(count):
                    if split == "train":
                        prompt = (
                            f"Design a playable {family} scenario with seed train-{i} "
                            "and clearly signposted decisions for the player."
                        )
                        answer = (
                            f"For {family}, provide mechanics, original objectives, player "
                            f"agency, recoverable outcomes and resource constraints. Train example {i}."
                        )
                    else:
                        # The HOLDOUT authoring template is intentionally
                        # different from training. Otherwise a six-gram leak
                        # check correctly rejects these synthetic fixtures.
                        prompt = (
                            f"Evaluate the {family} consequences of a confusing hidden "
                            f"route where a novice encounters setback heldout-{i}."
                        )
                        answer = (
                            f"Inspect {family} consequences after the detour, determine "
                            f"whether novices can return, and document alternatives. "
                            f"Evaluation example {i} with unique authored context."
                        )
                    rows.append({
                        "id": f"{split}_{family}_{i:03d}",
                        "source_project_id": f"authored_{split}_{family}_{i:03d}",
                        "split": split,
                        "family": family,
                        "prompt": prompt,
                        "answer": answer,
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

    def test_short_embedded_game_question_is_not_a_safe_holdout(self) -> None:
        from skeleton.ai.training.jeeves_game_corpus import _split_contamination
        self.assertTrue(_split_contamination(
            "Unlock hidden gate", "When exploring ruins, unlock hidden gate before sunset."
        ))
        self.assertTrue(_split_contamination("choose an ending", "choose an ending"))
        self.assertFalse(_split_contamination(
            "Repair a forest bridge", "Negotiate peace with strangers near the harbor."
        ))

    def test_loader_rejects_short_embedded_prompts_in_either_split(self) -> None:
        for short_is_heldout in (True, False):
            with self.subTest(short_is_heldout=short_is_heldout), tempfile.TemporaryDirectory() as d:
                train, heldout, regenerate = self._fixtures(Path(d))
                short = "Unlock hidden gate"
                long = "When exploring the ruins, unlock hidden gate before sunset."
                train[0]["prompt"], heldout[0]["prompt"] = (long, short) if short_is_heldout else (short, long)
                with self.assertRaisesRegex(ProductionCheckpointError, "prompt leaked"):
                    load_approved_corpus(regenerate())

    def test_loader_rejects_short_embedded_answers_in_either_split(self) -> None:
        for short_is_heldout in (True, False):
            with self.subTest(short_is_heldout=short_is_heldout), tempfile.TemporaryDirectory() as d:
                train, heldout, regenerate = self._fixtures(Path(d))
                short = "Restore broken lantern"
                long = "At dusk restore broken lantern before the storm reaches the village."
                train[0]["answer"], heldout[0]["answer"] = (long, short) if short_is_heldout else (short, long)
                with self.assertRaisesRegex(ProductionCheckpointError, "answer near-duplicates"):
                    load_approved_corpus(regenerate())

    def test_file_modification_invalidates_admission_sha(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, _, regenerate = self._fixtures(root)
            path = regenerate()
            with (root / "game-train.jsonl").open("ab") as output:
                output.write(b"{}\n")
            with self.assertRaisesRegex(ProductionCheckpointError, "SHA-256"):
                load_approved_corpus(path)

    def test_manifest_receipt_binds_the_bytes_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, _, regenerate = self._fixtures(Path(temp))
            manifest = regenerate()
            expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
            _, _, receipt = load_approved_corpus(manifest)
            self.assertEqual(receipt["manifest_sha256"], expected)
            self.assertEqual(receipt["manifest_path"], str(manifest.absolute()))

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

    def test_same_project_cannot_be_train_and_holdout(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            train, heldout, regenerate = self._fixtures(root)
            heldout[0]["source_project_id"] = train[0]["source_project_id"]
            with self.assertRaisesRegex(ProductionCheckpointError, "same source project"):
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


class BoundedCorpusSnapshotTests(unittest.TestCase):
    def _read(self, path: Path) -> bytes:
        return _read_bounded_regular_file(path, minimum=16, maximum=64, label="test corpus")

    def test_replacement_between_admission_and_open_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dataset.jsonl"
            path.write_bytes(b"original reviewed data")
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(b"unreviewed replacement")
            original_open = os.open
            opened = []

            def replace_then_open(name, flags):
                replacement.replace(path)
                descriptor = original_open(name, flags)
                opened.append(descriptor)
                return descriptor

            with patch("skeleton.ai.training.jeeves_game_corpus.os.open", side_effect=replace_then_open):
                with self.assertRaisesRegex(ProductionCheckpointError, "changed while being opened"):
                    self._read(path)
            self.assertEqual(len(opened), 1)
            with self.assertRaises(OSError):
                os.fstat(opened[0])

    def test_growth_during_read_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dataset.jsonl"
            path.write_bytes(b"original reviewed data")
            original_fstat = os.fstat
            calls = 0

            def mutate_before_final_stat(descriptor):
                nonlocal calls
                calls += 1
                if calls == 2:
                    with path.open("ab") as output:
                        output.write(b" changed after read")
                return original_fstat(descriptor)

            with patch("skeleton.ai.training.jeeves_game_corpus.os.fstat", side_effect=mutate_before_final_stat):
                with self.assertRaisesRegex(ProductionCheckpointError, "changed while being read"):
                    self._read(path)

    @unittest.skipUnless(hasattr(os, "mkfifo") and getattr(os, "O_NONBLOCK", 0), "POSIX FIFO required")
    def test_fifo_swap_is_rejected_without_waiting_for_a_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dataset.jsonl"
            path.write_bytes(b"original reviewed data")
            original_open = os.open

            def replace_with_fifo(name, flags):
                self.assertTrue(flags & os.O_NONBLOCK, "opening a swapped FIFO must not block")
                path.unlink()
                os.mkfifo(path)
                return original_open(name, flags)

            with patch("skeleton.ai.training.jeeves_game_corpus.os.open", side_effect=replace_with_fifo):
                with self.assertRaisesRegex(ProductionCheckpointError, "bounded regular file"):
                    self._read(path)

    def test_symlink_and_oversized_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dataset.jsonl"
            path.write_bytes(b"x" * 65)
            with self.assertRaisesRegex(ProductionCheckpointError, "bounded regular file"):
                self._read(path)
            link = path.with_suffix(".link")
            try:
                link.symlink_to(path)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(ProductionCheckpointError, "bounded regular file"):
                self._read(link)


if __name__ == "__main__":
    unittest.main()
