from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from skeleton.ai.runtime.inference import (
    LocalInferenceRequest,
    NativeRuntimeLocalModel,
    load_local_model_artifact,
)
from skeleton.ai.runtime.inference.train import build_native_transformer_artifact
from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights
from skeleton.ai.training.native_transformer import (
    GovernedTrainingDataset,
    NativeTrainingError,
    NativeTransformerTrainingConfig,
    TRAINING_SCOPE,
    corpus_digest,
    governed_dataset,
    normalization_digest,
    train_native_transformer_candidate,
)


RIGHTS_EVIDENCE = "a" * 64
IMPLEMENTATION = "c" * 64


def _documents() -> tuple[str, ...]:
    return (
        "alpha beta gamma alpha beta delta alpha beta gamma",
        "beta gamma delta beta gamma alpha beta gamma delta",
    )


def _dataset() -> GovernedTrainingDataset:
    return governed_dataset(
        dataset_id="dataset-native-test",
        source_id="source-native-test",
        documents=_documents(),
        rights_evidence_digest=RIGHTS_EVIDENCE,
        license_id="test-license",
    )


def _config(*, seed: int = 11, max_steps: int = 10_000):
    return NativeTransformerTrainingConfig(
        dim=8,
        context=16,
        heads=2,
        layers=1,
        feed_forward=8,
        norm="rms",
        ffn_kind="swiglu",
        bpe_merges=8,
        epochs=1,
        learning_rate=0.01,
        schedule="cosine",
        seed=seed,
        max_steps=max_steps,
    )


class TestNativeTransformerTraining(unittest.TestCase):
    def test_candidate_training_emits_reloadable_native_runtime_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "native-candidate.json"
            receipt = train_native_transformer_candidate(
                dataset=_dataset(),
                output_path=output,
                candidate_id="candidate-native-test",
                config=_config(),
                implementation_digest=IMPLEMENTATION,
            )

            self.assertTrue(output.is_file())
            self.assertFalse(receipt.production_authorized)
            self.assertNotEqual(
                receipt.base_model_digest,
                receipt.trained_model_digest,
            )
            self.assertGreater(receipt.completed_steps, 0)
            self.assertEqual(
                receipt.completed_steps,
                receipt.planned_steps,
            )
            self.assertEqual(receipt.document_count, len(_documents()))
            self.assertGreater(receipt.initial_perplexity, 0.0)
            self.assertGreater(receipt.final_perplexity, 0.0)

            loaded = load_local_model_artifact(output)
            self.assertIsInstance(loaded.model, NativeRuntimeLocalModel)
            self.assertEqual(
                loaded.model.model_digest,
                receipt.trained_model_digest,
            )
            self.assertEqual(
                loaded.model.tokenizer_digest,
                receipt.tokenizer_digest,
            )
            self.assertEqual(
                loaded.receipt.artifact_sha256,
                receipt.artifact_sha256,
            )

            result = loaded.model.infer(
                LocalInferenceRequest(
                    prompt="alpha beta",
                    max_output_tokens=3,
                    seed=7,
                ),
                threading.Event(),
            )
            self.assertTrue(result.text)
            self.assertGreater(result.input_tokens, 0)
            self.assertGreater(result.output_tokens, 0)
            self.assertLessEqual(result.output_tokens, 3)

    def test_same_corpus_config_seed_and_code_produce_same_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = train_native_transformer_candidate(
                dataset=_dataset(),
                output_path=root / "first.json",
                candidate_id="candidate-deterministic",
                config=_config(seed=19),
                implementation_digest=IMPLEMENTATION,
            )
            second = train_native_transformer_candidate(
                dataset=_dataset(),
                output_path=root / "second.json",
                candidate_id="candidate-deterministic",
                config=_config(seed=19),
                implementation_digest=IMPLEMENTATION,
            )

            self.assertEqual(
                first.trained_model_digest,
                second.trained_model_digest,
            )
            self.assertEqual(first.tokenizer_digest, second.tokenizer_digest)
            self.assertEqual(first.artifact_sha256, second.artifact_sha256)
            self.assertEqual(
                first.training_manifest_digest,
                second.training_manifest_digest,
            )
            self.assertEqual(first.checkpoint_digest, second.checkpoint_digest)
            self.assertEqual(first.candidate_digest, second.candidate_digest)
            self.assertEqual(first.digest, second.digest)

    def test_seed_changes_candidate_weight_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = train_native_transformer_candidate(
                dataset=_dataset(),
                output_path=root / "seed-1.json",
                candidate_id="candidate-seed-1",
                config=_config(seed=1),
                implementation_digest=IMPLEMENTATION,
            )
            second = train_native_transformer_candidate(
                dataset=_dataset(),
                output_path=root / "seed-2.json",
                candidate_id="candidate-seed-2",
                config=_config(seed=2),
                implementation_digest=IMPLEMENTATION,
            )
            self.assertNotEqual(
                first.trained_model_digest,
                second.trained_model_digest,
            )
            self.assertNotEqual(first.artifact_sha256, second.artifact_sha256)

    def test_training_step_budget_fails_before_artifact_write(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "denied.json"
            with self.assertRaisesRegex(
                NativeTrainingError,
                "planned training exceeds configured step budget",
            ):
                train_native_transformer_candidate(
                    dataset=_dataset(),
                    output_path=output,
                    candidate_id="candidate-over-budget",
                    config=_config(max_steps=1),
                    implementation_digest=IMPLEMENTATION,
                )
            self.assertFalse(output.exists())

    def test_dataset_rights_and_content_drift_fail_closed(self):
        docs = _documents()
        allowed = DatasetRights(
            dataset_id="dataset-drift",
            source_id="source-drift",
            rights_status="allowed",
            license_id=None,
            allowed_scopes=(TRAINING_SCOPE,),
            evidence_digest=RIGHTS_EVIDENCE,
        )
        good_revision = DatasetRevision(
            dataset_id="dataset-drift",
            revision=0,
            content_digest=corpus_digest(docs),
            rights_digest=allowed.digest,
            transform_digest=normalization_digest(),
        )
        GovernedTrainingDataset(allowed, good_revision, docs)

        denied = DatasetRights(
            dataset_id="dataset-drift",
            source_id="source-drift",
            rights_status="allowed",
            license_id=None,
            allowed_scopes=("evaluation-only",),
            evidence_digest=RIGHTS_EVIDENCE,
        )
        denied_revision = DatasetRevision(
            dataset_id="dataset-drift",
            revision=0,
            content_digest=corpus_digest(docs),
            rights_digest=denied.digest,
            transform_digest=normalization_digest(),
        )
        with self.assertRaisesRegex(
            NativeTrainingError,
            "rights do not permit",
        ):
            GovernedTrainingDataset(denied, denied_revision, docs)

        bad_content = DatasetRevision(
            dataset_id="dataset-drift",
            revision=0,
            content_digest="b" * 64,
            rights_digest=allowed.digest,
            transform_digest=normalization_digest(),
        )
        with self.assertRaisesRegex(
            NativeTrainingError,
            "content digest mismatch",
        ):
            GovernedTrainingDataset(allowed, bad_content, docs)

    def test_file_builder_emits_candidate_only_local_provider_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root / "corpus.txt"
            corpus.write_text("\n".join(_documents()), encoding="utf-8")
            output = root / "native.json"

            receipt = build_native_transformer_artifact(
                corpus_paths=(corpus,),
                output_path=output,
                candidate_id="candidate-builder",
                dataset_id="dataset-builder",
                source_id="source-builder",
                rights_evidence_digest=RIGHTS_EVIDENCE,
                license_id="test-license",
                dim=8,
                context=16,
                heads=2,
                layers=1,
                feed_forward=8,
                bpe_merges=8,
                epochs=1,
                learning_rate=0.01,
                schedule="cosine",
                seed=31,
                max_steps=10_000,
                implementation_digest=IMPLEMENTATION,
            )

            self.assertEqual(receipt["runtime_kind"], "native-transformer")
            self.assertEqual(
                receipt["artifact_schema"],
                "skeleton.ai.native-llm-runtime.v2",
            )
            self.assertTrue(receipt["credential_free"])
            self.assertTrue(receipt["candidate_only"])
            self.assertFalse(receipt["production_authorized"])
            self.assertEqual(len(receipt["rights_digest"]), 64)
            self.assertEqual(len(receipt["training_receipt_digest"]), 64)
            loaded = load_local_model_artifact(output)
            self.assertIsInstance(loaded.model, NativeRuntimeLocalModel)


if __name__ == "__main__":
    unittest.main()
