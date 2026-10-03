from __future__ import annotations

import json
import threading

import pytest

from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.runtime.inference.training_methods import (
    TrainingExample,
    TrainingMethod,
)


def test_gated_recurrent_training_is_deterministic() -> None:
    pytest.importorskip("numpy")
    from skeleton.ai.runtime.inference.gated_neural import (
        NumpyGatedRecurrentLM,
    )

    corpus = (
        "user asks for alpha assistant returns beta",
        "alpha maps to beta",
    )
    first = NumpyGatedRecurrentLM.train(
        corpus,
        model_id="gru-deterministic",
        hidden_size=8,
        epochs=2,
        learning_rate=0.03,
        max_vocab=32,
        max_document_tokens=32,
        seed=17,
        temperature=0.7,
        gradient_accumulation_steps=2,
    )
    second = NumpyGatedRecurrentLM.train(
        corpus,
        model_id="gru-deterministic",
        hidden_size=8,
        epochs=2,
        learning_rate=0.03,
        max_vocab=32,
        max_document_tokens=32,
        seed=17,
        temperature=0.7,
        gradient_accumulation_steps=2,
    )

    assert first.model_digest == second.model_digest
    assert first.to_dict() == second.to_dict()
    assert first.training_loss_history == second.training_loss_history
    assert len(first.training_loss_history) == 2
    assert all(value >= 0.0 for value in first.training_loss_history)
    assert first.training_optimizer_steps > 0


def test_gated_recurrent_artifact_round_trips_and_infers(tmp_path) -> None:
    pytest.importorskip("numpy")
    from skeleton.ai.runtime.inference.gated_neural import (
        NumpyGatedRecurrentLM,
    )

    model = NumpyGatedRecurrentLM.train(
        ("answer red", "answer red object"),
        model_id="gru-roundtrip",
        hidden_size=8,
        epochs=2,
        learning_rate=0.03,
        max_vocab=32,
        max_document_tokens=32,
        seed=23,
        temperature=0.7,
    )
    path = tmp_path / "gated.json"
    path.write_text(
        json.dumps(
            model.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    loaded = load_local_model_artifact(path)
    assert loaded.receipt.schema == "skeleton.numpy_gated_recurrent_lm.v1"
    assert loaded.receipt.model_digest == model.model_digest

    request = LocalInferenceRequest(
        prompt="answer",
        max_output_tokens=6,
        seed=9,
    )
    first = loaded.model.infer(request, threading.Event())
    second = loaded.model.infer(request, threading.Event())

    assert first.model_digest == model.model_digest
    assert first.response_id == second.response_id
    assert first.text == second.text
    assert first.output_tokens >= 0


def test_multi_method_builder_defaults_to_gated_recurrent(tmp_path) -> None:
    pytest.importorskip("numpy")
    from skeleton.ai.runtime.inference.train import (
        build_multi_method_recurrent_artifact,
    )

    output = tmp_path / "multi-gated.json"
    receipt = build_multi_method_recurrent_artifact(
        examples=(
            TrainingExample(
                example_id="gated-multi",
                prompt="Question",
                response="Answer",
            ),
        ),
        output_path=output,
        model_id="multi-gated",
        methods=(
            TrainingMethod.SUPERVISED_INSTRUCTION,
            TrainingMethod.CAUSAL_LANGUAGE_MODELING,
        ),
        hidden_size=8,
        epochs=1,
        learning_rate=0.03,
        max_vocab=32,
        max_document_tokens=32,
        seed=29,
        temperature=0.7,
    )

    assert receipt["model_architecture"] == "gated_recurrent"
    assert receipt["schema"] == "skeleton.numpy_gated_recurrent_lm.v1"
    loaded = load_local_model_artifact(output)
    assert loaded.receipt.model_digest == receipt["model_digest"]


def test_plain_builder_keeps_legacy_default_and_can_opt_into_gated(
    tmp_path,
) -> None:
    pytest.importorskip("numpy")
    from skeleton.ai.runtime.inference.train import build_recurrent_artifact

    corpus = tmp_path / "corpus.txt"
    corpus.write_text("alpha beta gamma", encoding="utf-8")

    legacy = build_recurrent_artifact(
        corpus_paths=(corpus,),
        output_path=tmp_path / "legacy.json",
        model_id="legacy-default",
        hidden_size=8,
        epochs=1,
        max_vocab=32,
        max_document_tokens=32,
    )
    gated = build_recurrent_artifact(
        corpus_paths=(corpus,),
        output_path=tmp_path / "gated-opt-in.json",
        model_id="gated-opt-in",
        hidden_size=8,
        epochs=1,
        max_vocab=32,
        max_document_tokens=32,
        model_architecture="gated_recurrent",
    )

    assert legacy["model_architecture"] == "elman_recurrent"
    assert legacy["schema"] == "skeleton.numpy_recurrent_lm.v1"
    assert gated["model_architecture"] == "gated_recurrent"
    assert gated["schema"] == "skeleton.numpy_gated_recurrent_lm.v1"
