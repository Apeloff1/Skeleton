from __future__ import annotations

from pathlib import Path
import threading

import pytest

from skeleton.ai.runtime.inference import (
    LocalInferenceRequest,
    NativeRuntimeLocalModel,
    load_local_model_artifact,
)
from skeleton.ai.runtime.inference.train import build_native_transformer_artifact
from skeleton.ai.training.native_transformer import (
    NativeTrainingError,
    NativeTransformerTrainingConfig,
    governed_dataset,
    train_native_transformer_candidate,
)


RIGHTS = "a" * 64
CODE = "c" * 64


def _docs():
    return (
        "alpha beta gamma alpha beta delta alpha beta gamma",
        "beta gamma delta beta gamma alpha beta gamma delta",
    )


def _config(seed=17, max_steps=10_000):
    return NativeTransformerTrainingConfig(
        dim=8,
        context=16,
        heads=2,
        layers=1,
        feed_forward=8,
        bpe_merges=8,
        epochs=1,
        learning_rate=0.01,
        schedule="cosine",
        seed=seed,
        max_steps=max_steps,
    )


def _dataset():
    return governed_dataset(
        dataset_id="p2-native-training",
        source_id="p2-native-source",
        documents=_docs(),
        rights_evidence_digest=RIGHTS,
        license_id="test-license",
    )


def test_native_candidate_artifact_reloads_and_executes(tmp_path: Path) -> None:
    output = tmp_path / "candidate.json"
    receipt = train_native_transformer_candidate(
        dataset=_dataset(),
        output_path=output,
        candidate_id="p2-native-candidate",
        config=_config(),
        implementation_digest=CODE,
    )

    assert receipt.production_authorized is False
    assert receipt.trained_model_digest != receipt.base_model_digest
    assert receipt.completed_steps == receipt.planned_steps
    loaded = load_local_model_artifact(output)
    assert isinstance(loaded.model, NativeRuntimeLocalModel)
    assert loaded.model.model_digest == receipt.trained_model_digest
    assert loaded.model.tokenizer_digest == receipt.tokenizer_digest

    result = loaded.model.infer(
        LocalInferenceRequest(
            prompt="alpha beta",
            max_output_tokens=3,
            seed=5,
        ),
        threading.Event(),
    )
    assert result.text
    assert 0 < result.output_tokens <= 3


def test_native_training_is_reproducible(tmp_path: Path) -> None:
    first = train_native_transformer_candidate(
        dataset=_dataset(),
        output_path=tmp_path / "first.json",
        candidate_id="p2-replay",
        config=_config(seed=23),
        implementation_digest=CODE,
    )
    second = train_native_transformer_candidate(
        dataset=_dataset(),
        output_path=tmp_path / "second.json",
        candidate_id="p2-replay",
        config=_config(seed=23),
        implementation_digest=CODE,
    )

    assert first.trained_model_digest == second.trained_model_digest
    assert first.tokenizer_digest == second.tokenizer_digest
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.digest == second.digest


def test_native_training_budget_denial_does_not_create_artifact(
    tmp_path: Path,
) -> None:
    output = tmp_path / "denied.json"
    with pytest.raises(
        NativeTrainingError,
        match="planned training exceeds configured step budget",
    ):
        train_native_transformer_candidate(
            dataset=_dataset(),
            output_path=output,
            candidate_id="p2-denied",
            config=_config(max_steps=1),
            implementation_digest=CODE,
        )
    assert not output.exists()


def test_native_file_builder_is_candidate_only(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("\n".join(_docs()), encoding="utf-8")
    output = tmp_path / "native.json"

    receipt = build_native_transformer_artifact(
        corpus_paths=(corpus,),
        output_path=output,
        candidate_id="p2-builder",
        dataset_id="p2-builder-dataset",
        source_id="p2-builder-source",
        rights_evidence_digest=RIGHTS,
        dim=8,
        context=16,
        heads=2,
        layers=1,
        feed_forward=8,
        bpe_merges=8,
        epochs=1,
        learning_rate=0.01,
        seed=29,
        max_steps=10_000,
        implementation_digest=CODE,
    )

    assert receipt["runtime_kind"] == "native-transformer"
    assert receipt["candidate_only"] is True
    assert receipt["production_authorized"] is False
    assert receipt["credential_free"] is True
    assert load_local_model_artifact(output).receipt.model_digest == receipt["model_digest"]
