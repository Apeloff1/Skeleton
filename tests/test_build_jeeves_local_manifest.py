"""Create-only local Jeeves model manifest contracts.

Tests isolate publication logic from the real native binary. Actual GGUF
loading and real generation are separately proved on the model host; these
tests never claim that a test double was an installed model.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import build_jeeves_local_manifest as builder
from skeleton.ai.runtime.inference.deployment import LocalModelDeploymentError


def identity(**overrides):
    fields = {
        "model_id": "jeeves",
        "model_sha256": "a" * 64,
        "executable_sha256": "b" * 64,
        "manifest_digest": "c" * 64,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_jeeves_manifest_pins_original_model_and_executable_without_retraining(
    tmp_path, monkeypatch
):
    destination = tmp_path / "jeeves.json"
    calls = []
    def create(target, **kwargs):
        calls.append((target, kwargs))
        return identity()
    def reload(target):
        assert target == destination
        return identity()
    monkeypatch.setattr(builder, "create_local_model_deployment", create)
    monkeypatch.setattr(builder.LocalModelDeployment, "load", reload)
    result = builder.prepare_manifest(
        destination, executable=tmp_path / "llama-cli",
        model=tmp_path / "licensed.gguf", profile="raw", context_size=8192,
        gpu_layers=0, threads=4,
    )
    assert result["ok"] is True
    assert result["provider"] == "local"
    assert result["model_id"] == "jeeves"
    assert result["model_sha256"] == "a" * 64
    assert result["runtime_sha256"] == "b" * 64
    assert result["network_required"] is False
    assert result["inference_verified"] is False
    assert result["underlying_weights_retrained"] is False
    assert len(calls) == 1
    assert calls[0][1]["model_id"] == "jeeves"
    assert calls[0][1]["runtime_profile"] == "raw"
    assert calls[0][1]["model_path"] == tmp_path / "licensed.gguf"


@pytest.mark.parametrize("profile", ["hosted", "", "unknown", "QWEN3", "proxy"])
def test_manifest_rejects_nonlocal_or_unsupported_runtime_profile(
    tmp_path, monkeypatch, profile
):
    monkeypatch.setattr(
        builder, "create_local_model_deployment",
        lambda *_a, **_kw: pytest.fail("invalid profile reached model publication"),
    )
    with pytest.raises(ValueError, match="supported local text generation profile"):
        builder.prepare_manifest(
            tmp_path / "jeeves.json",
            executable=tmp_path / "llama-cli",
            model=tmp_path / "model.gguf",
            profile=profile,
        )


def test_manifest_refuses_replacement_of_existing_model_binding(tmp_path, monkeypatch):
    destination = tmp_path / "jeeves.json"
    destination.write_text("old identity", encoding="utf-8")
    monkeypatch.setattr(
        builder, "create_local_model_deployment",
        lambda *_a, **_kw: pytest.fail("existing model must remain unchanged"),
    )
    with pytest.raises(LocalModelDeploymentError, match="already exists"):
        builder.prepare_manifest(
            destination, executable=tmp_path / "llama-cli",
            model=tmp_path / "model.gguf",
        )
    assert destination.read_text() == "old identity"


@pytest.mark.parametrize("changed", [
    {"model_id": "gpt-5.5"},
    {"model_id": "untrusted"},
    {"model_sha256": "d" * 64},
    {"executable_sha256": "d" * 64},
    {"manifest_digest": "d" * 64},
])
def test_publication_reloads_model_and_denies_identity_drift(tmp_path, monkeypatch, changed):
    monkeypatch.setattr(
        builder, "create_local_model_deployment",
        lambda *_a, **_kw: identity(),
    )
    monkeypatch.setattr(
        builder.LocalModelDeployment, "load",
        lambda *_a, **_kw: identity(**changed),
    )
    with pytest.raises(LocalModelDeploymentError, match="did not retain"):
        builder.prepare_manifest(
            tmp_path / "jeeves.json", executable=tmp_path / "llama-cli",
            model=tmp_path / "licensed.gguf",
        )


def test_no_model_files_or_inference_are_created_without_operator_sources(tmp_path):
    result = builder.main([
        "--model", str(tmp_path / "does-not-exist.gguf"),
        "--executable", str(tmp_path / "does-not-exist-llama"),
        "--output", str(tmp_path / "jeeves.json"),
    ])
    assert result == 2
    assert not (tmp_path / "jeeves.json").exists()
