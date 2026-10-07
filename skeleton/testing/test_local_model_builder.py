from __future__ import annotations

import json
from pathlib import Path
import threading

import pytest

from skeleton.ai.runtime.inference.artifact import (
    LocalModelArtifactError,
    load_local_model_artifact,
)
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.runtime.inference.train import build_recurrent_artifact


def _corpus(tmp_path: Path) -> Path:
    path = tmp_path / "corpus.txt"
    path.write_text(
        "local intelligence learns locally.\n"
        "local intelligence keeps deterministic identity.\n",
        encoding="utf-8",
    )
    return path


def test_training_cli_target_builds_reloadable_native_artifact(
    tmp_path: Path,
) -> None:
    pytest.importorskip("numpy")
    corpus = _corpus(tmp_path)
    output = tmp_path / "model.json"

    receipt = build_recurrent_artifact(
        corpus_paths=(corpus,),
        output_path=output,
        model_id="builder-test",
        hidden_size=8,
        epochs=2,
        learning_rate=0.03,
        seed=17,
    )

    assert output.is_file()
    assert receipt["credential_free"] is True
    assert receipt["final_loss"] < receipt["initial_loss"]
    loaded = load_local_model_artifact(output)
    assert loaded.receipt.model_id == "builder-test"
    assert loaded.receipt.model_digest == receipt["model_digest"]
    assert loaded.receipt.artifact_sha256 == receipt["artifact_sha256"]

    result = loaded.model.infer(
        LocalInferenceRequest(
            prompt="local intelligence",
            max_output_tokens=8,
            seed=17,
        ),
        threading.Event(),
    )
    assert result.model_digest == receipt["model_digest"]
    assert result.text


def test_same_seed_corpus_and_config_build_same_model_identity(
    tmp_path: Path,
) -> None:
    pytest.importorskip("numpy")
    corpus = _corpus(tmp_path)
    first = build_recurrent_artifact(
        corpus_paths=(corpus,),
        output_path=tmp_path / "first.json",
        model_id="replay-builder",
        hidden_size=8,
        epochs=1,
        learning_rate=0.02,
        seed=9,
    )
    second = build_recurrent_artifact(
        corpus_paths=(corpus,),
        output_path=tmp_path / "second.json",
        model_id="replay-builder",
        hidden_size=8,
        epochs=1,
        learning_rate=0.02,
        seed=9,
    )
    assert first["model_digest"] == second["model_digest"]
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["training_receipt_digest"] == second["training_receipt_digest"]


def test_artifact_tamper_is_rejected(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    corpus = _corpus(tmp_path)
    output = tmp_path / "model.json"
    build_recurrent_artifact(
        corpus_paths=(corpus,),
        output_path=output,
        model_id="tamper-test",
        hidden_size=8,
        epochs=1,
        seed=3,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["model_digest"] = "0" * 64
    output.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelArtifactError, match="identity validation"):
        load_local_model_artifact(output)


def test_duplicate_corpus_path_fails_closed(tmp_path: Path) -> None:
    from skeleton.ai.runtime.inference.train import LocalModelBuildError

    corpus = _corpus(tmp_path)
    with pytest.raises(LocalModelBuildError, match="duplicate corpus"):
        build_recurrent_artifact(
            corpus_paths=(corpus, corpus),
            output_path=tmp_path / "model.json",
            model_id="duplicate-corpus",
            hidden_size=8,
            epochs=1,
        )
