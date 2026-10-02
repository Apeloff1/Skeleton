from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from skeleton.ai.runtime.inference import (
    load_local_model_artifact,
    local_model_adapter_from_env,
)
from skeleton.ai.runtime.inference.train import (
    LocalModelBuildError,
    build_recurrent_artifact,
)


def test_offline_builder_trains_promotes_and_boots_exact_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus_a = tmp_path / "a.txt"
    corpus_b = tmp_path / "b.txt"
    corpus_a.write_text(
        "alpha beta gamma\n\nalpha beta delta",
        encoding="utf-8",
    )
    corpus_b.write_text(
        "beta gamma alpha\n\ngamma alpha beta",
        encoding="utf-8",
    )
    output = tmp_path / "local-rnn.json"

    receipt = build_recurrent_artifact(
        corpus_paths=(corpus_a, corpus_b),
        output_path=output,
        model_id="builder-rnn-test",
        hidden_size=10,
        epochs=2,
        learning_rate=0.08,
        max_vocab=32,
        max_document_tokens=32,
        seed=17,
        temperature=0.7,
    )

    assert output.is_file()
    assert receipt["schema"] == "skeleton.numpy_recurrent_lm.v1"
    assert receipt["model_id"] == "builder-rnn-test"
    assert receipt["training_documents"] == 4
    assert receipt["hidden_size"] == 10
    assert receipt["vocab_size"] >= 3

    loaded = load_local_model_artifact(output)
    assert loaded.receipt.model_digest == receipt["model_digest"]
    assert loaded.receipt.artifact_sha256 == receipt["artifact_sha256"]

    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(output))
    monkeypatch.setenv("AI_LOCAL_MODEL_CACHE_SIZE", "3")
    monkeypatch.setenv("AI_LOCAL_MODEL_SEED", "17")
    adapter = local_model_adapter_from_env()

    assert adapter.provider_id == "local"
    assert adapter.model == "builder-rnn-test"
    assert adapter.engine.cache_size == 3
    assert adapter.default_seed == 17
    assert adapter.artifact_receipt.model_digest == receipt["model_digest"]


def test_offline_builder_rejects_missing_parent_or_oversized_inputs(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("small corpus", encoding="utf-8")

    with pytest.raises(
        LocalModelBuildError,
        match="parent directory",
    ):
        build_recurrent_artifact(
            corpus_paths=(corpus,),
            output_path=tmp_path / "missing" / "model.json",
            model_id="invalid-output",
            hidden_size=8,
            epochs=1,
        )

    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(
        LocalModelBuildError,
        match="byte bounds",
    ):
        build_recurrent_artifact(
            corpus_paths=(empty,),
            output_path=tmp_path / "unused.json",
            model_id="empty-corpus",
            hidden_size=8,
            epochs=1,
        )


def test_builder_output_is_strict_finite_json(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text(
        "one two three\none two four",
        encoding="utf-8",
    )
    output = tmp_path / "model.json"
    receipt = build_recurrent_artifact(
        corpus_paths=(corpus,),
        output_path=output,
        model_id="strict-json-rnn",
        hidden_size=8,
        epochs=1,
        seed=5,
    )

    payload = json.loads(
        output.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            AssertionError("non-finite JSON constant: " + value)
        ),
    )
    assert payload["schema_version"] == "skeleton.numpy_recurrent_lm.v1"
    assert payload["model_digest"] == receipt["model_digest"]
