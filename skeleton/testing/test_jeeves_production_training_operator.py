"""Small offline contracts for production Jeeves game-training admission.

No copied RNN model may satisfy attestation. No weights are promoted. These
tests do not pretend to be an end-to-end compiled-app acceptance run.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.ai.training.jeeves_production_game_train import (
    ProductionCheckpointError, _active_snapshot,
)
from skeleton.ai.training.jeeves_production_readiness import (
    SCHEMA as ATTEST_SCHEMA,
    _canonical, _load_attestation, _save_new_private, inspect,
    prepare_training_copy, attest_running_cortex,
)
from skeleton.ai.training.jeeves_production_game_session import run
from skeleton.ai.training.jeeves_game_design_benchmark import (
    BENCHMARK, _simple_diagnostics, compare,
)
from skeleton.ai.training.jeeves_game_vocabulary import (
    expand_native_game_pieces, planned_new_pieces,
)


class ProductionGameReadinessTests(unittest.TestCase):
    def test_no_checkpoint_environment_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"SKELETON_OWN": ""}):
                result = inspect(
                    candidate_directory=Path(temp),
                    attestation=None,
                    minimum_free_bytes=0,
                )
            self.assertEqual(result["status"], "blocked")
            self.assertIn("SKELETON_OWN_not_configured", result["blockers"])
            self.assertIn("missing_in_process_serving_attestation", result["blockers"])
            self.assertFalse(result["production_training_executed"])

    def test_dry_run_does_not_fake_training_or_create_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.dict(os.environ, {"SKELETON_OWN": ""}):
                result = run(
                    run_id="game-run-001",
                    attestation=root / "missing-attestation.json",
                    output_directory=root,
                    dry_run=True,
                )
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["training_executed"])
            self.assertFalse(result["candidate_promoted"])
            self.assertEqual(list(root.iterdir()), [])

    def test_checkpoint_custody_cannot_attest_arbitrary_cortex(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ProductionCheckpointError, "in-process"):
                attest_running_cortex(object(), Path(temp) / "fake.json")

    def test_exclusive_receipt_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "attestation.json"
            _save_new_private(target, b"one\n")
            with self.assertRaisesRegex(ProductionCheckpointError, "new path"):
                _save_new_private(target, b"two\n")
            self.assertEqual(target.read_bytes(), b"one\n")

    def test_reject_modified_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "forged.json"
            value = {
                "schema_version": ATTEST_SCHEMA,
                "source": "in_process_live_jeeves",
                "pid": 100,
                "created_unix": int(time.time()),
                "production_restored": True,
            }
            value["receipt_sha256"] = "0" * 64
            target.write_bytes(_canonical(value))
            with self.assertRaisesRegex(ProductionCheckpointError, "modified"):
                _load_attestation(target, maximum_age_seconds=60)

    def test_attestation_age_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "receipt.json"
            for age in (3601, -61):
                value = {
                    "schema_version": ATTEST_SCHEMA,
                    "source": "in_process_live_jeeves",
                    "pid": 100,
                    "created_unix": int(time.time()) - age,
                    "production_restored": True,
                }
                value["receipt_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
                path.write_bytes(_canonical(value))
                with self.assertRaisesRegex(ProductionCheckpointError, "expired"):
                    _load_attestation(path, maximum_age_seconds=60)

    def test_backup_cannot_proceed_without_custody(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.dict(os.environ, {"SKELETON_OWN": ""}):
                with self.assertRaisesRegex(ProductionCheckpointError, "preflight blocked"):
                    prepare_training_copy(
                        attestation=root / "no-attestation.json",
                        candidate_directory=root,
                        copy_destination=root / "backup.json",
                    )
            self.assertFalse((root / "backup.json").exists())


class GameVocabPreservationTests(unittest.TestCase):
    def _model(self):
        from skeleton.cortex.bpe import BytePairEncoder
        from skeleton.cortex.transformer import TinyTransformer
        bpe = BytePairEncoder(merges=4)
        bpe.fit((
            "build a branching quest gate and puzzle",
            "track story continuity and npc memory",
        ))
        model = TinyTransformer(vocab=["other", "unrelated"], dim=8, ctx=6, seed=11)
        model.bpe = bpe
        return model

    def test_expand_only_untrained_rows_and_preserve_existing_ids(self) -> None:
        model = self._model()
        original_tokens = tuple(model.itos)
        old_weights = [list(row) for row in model.E]
        original_bias = list(model.bout)
        docs = ("User: Design a branching quest. Jeeves: Track memory.",)
        missing = planned_new_pieces(model, docs)
        self.assertGreater(len(missing), 0)
        receipt = expand_native_game_pieces(model, docs, expected_snapshot_digest="a" * 64)
        self.assertEqual(receipt["new_tokens"], len(missing))
        self.assertEqual(tuple(model.itos[:len(original_tokens)]), original_tokens)
        self.assertEqual(model.E[:len(old_weights)], old_weights)
        self.assertEqual(model.bout[:len(original_bias)], original_bias)
        self.assertEqual(len(model.E), len(model.Wout))
        self.assertEqual(len(model.E), len(model.bout))
        self.assertEqual(planned_new_pieces(model, docs), ())
        from skeleton.cortex.transformer import TinyTransformer
        restored = TinyTransformer.from_snapshot(model.snapshot())
        restored.bpe = model.bpe
        self.assertEqual(restored.itos, model.itos)
        self.assertEqual(restored._ids(docs[0]), model._ids(docs[0]))

    def test_expansion_is_deterministic_for_same_checkpoint_digest(self) -> None:
        x, y = self._model(), self._model()
        docs = ("User: Design new dialogue and exploration.",)
        a = expand_native_game_pieces(x, docs, expected_snapshot_digest="b" * 64)
        b = expand_native_game_pieces(y, docs, expected_snapshot_digest="b" * 64)
        self.assertEqual(a, b)
        self.assertEqual(x.snapshot(), y.snapshot())

    def test_bad_digest_does_not_modify_weights(self) -> None:
        model = self._model()
        original = model.snapshot()
        with self.assertRaisesRegex(ProductionCheckpointError, "digest"):
            expand_native_game_pieces(
                model, ("User: New game.",), expected_snapshot_digest="invalid",
            )
        self.assertEqual(model.snapshot(), original)


class GameBenchmarkTests(unittest.TestCase):
    def test_references_are_separate_and_have_eight_domains(self) -> None:
        self.assertEqual(len(BENCHMARK), 24)
        self.assertEqual(len({row[0] for row in BENCHMARK}), 8)
        self.assertEqual(len({row[1] for row in BENCHMARK}), 24)

    def test_lexical_coverage_never_certifies_gameplay(self) -> None:
        report = _simple_diagnostics("Input with recovery", ("input", "recovery"))
        self.assertEqual(len(report["diagnostic_terms_present"]), 2)
        self.assertTrue(report["requires_independent_review"])

    def test_cannot_score_same_checkpoint_as_parent_and_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "same.json"
            path.write_text('{"own":{}}', encoding="utf-8")
            with self.assertRaisesRegex(ProductionCheckpointError, "different files"):
                compare(path, path, expected_parent_sha256="0" * 64)

    def test_no_silent_mouth_fallback(self) -> None:
        with self.assertRaisesRegex(ProductionCheckpointError, "unsupported active"):
            _active_snapshot({"winner": "pfc", "transformer": {}})


if __name__ == "__main__":
    unittest.main()
