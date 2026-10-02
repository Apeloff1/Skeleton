from __future__ import annotations

import json
import threading

import pytest

np = pytest.importorskip("numpy")

from skeleton.ai.runtime.inference.artifact import (
    LocalModelArtifactError,
    load_local_model_artifact,
)
from skeleton.ai.runtime.inference.local import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
)
from skeleton.ai.runtime.inference.neural import NumpyRecurrentLM


def _trained() -> NumpyRecurrentLM:
    return NumpyRecurrentLM.train(
        (
            "alpha beta gamma",
            "alpha beta delta",
            "beta gamma alpha",
            "gamma alpha beta",
        ),
        model_id="numpy-rnn-test",
        hidden_size=12,
        epochs=3,
        learning_rate=0.08,
        max_vocab=32,
        max_document_tokens=32,
        seed=7,
        temperature=0.7,
    )


def test_numpy_recurrent_training_is_deterministic() -> None:
    first = _trained()
    second = _trained()

    assert first.model_id == "numpy-rnn-test"
    assert first.model_digest == second.model_digest
    assert first.vocab == second.vocab
    assert np.array_equal(first.embedding, second.embedding)
    assert np.array_equal(first.recurrent, second.recurrent)
    assert np.array_equal(first.output, second.output)


def test_numpy_recurrent_artifact_round_trip_and_digest(tmp_path) -> None:
    model = _trained()
    path = tmp_path / "numpy-rnn.json"
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

    assert loaded.receipt.schema == "skeleton.numpy_recurrent_lm.v1"
    assert loaded.receipt.model_id == model.model_id
    assert loaded.receipt.model_digest == model.model_digest
    assert isinstance(loaded.model, NumpyRecurrentLM)
    assert loaded.model.model_digest == model.model_digest


@pytest.mark.asyncio
async def test_numpy_recurrent_local_engine_is_seed_deterministic() -> None:
    model = _trained()
    engine = LocalInferenceEngine(model, cache_size=0)
    request = LocalInferenceRequest(
        prompt="alpha beta",
        instructions="Continue the learned local sequence.",
        max_output_tokens=8,
        seed=123,
    )

    first = await engine.generate(request)
    second = await engine.generate(request)

    assert first.model_id == model.model_id
    assert first.model_digest == model.model_digest
    assert first.text == second.text
    assert first.response_id == second.response_id
    assert first.input_tokens > 0
    assert first.output_tokens >= 0


def test_numpy_recurrent_inference_observes_cancellation() -> None:
    model = _trained()
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(
        LocalInferenceCancelled,
        match="cancelled",
    ):
        model.infer(
            LocalInferenceRequest(
                prompt="alpha",
                max_output_tokens=8,
            ),
            cancel,
        )


def test_numpy_recurrent_artifact_rejects_weight_tampering(tmp_path) -> None:
    model = _trained()
    payload = model.to_dict()
    payload["embedding"][0][0] = float(payload["embedding"][0][0]) + 0.5
    path = tmp_path / "tampered-rnn.json"
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        LocalModelArtifactError,
        match="invalid",
    ):
        load_local_model_artifact(path)


def test_numpy_recurrent_rejects_non_finite_or_shape_drift() -> None:
    model = _trained()
    payload = model.to_dict()
    payload["recurrent"] = payload["recurrent"][:-1]

    with pytest.raises(ValueError, match="shape"):
        NumpyRecurrentLM.from_dict(payload)

    payload = model.to_dict()
    payload["output_bias"][0] = float("inf")
    with pytest.raises(ValueError, match="non-finite"):
        NumpyRecurrentLM.from_dict(payload)
