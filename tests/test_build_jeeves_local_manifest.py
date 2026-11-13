"""Create-only local Jeeves model manifest contracts.

Tests isolate publication logic from the real native binary. Actual GGUF
loading and real generation are separately proved on the model host; these
tests never claim that a test double was an installed model.
"""
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest

from scripts import build_jeeves_local_manifest as builder
from skeleton.ai.runtime.inference.deployment import (
    CODING_COMPLETION_CHAT_TEMPLATE, LOCAL_MODEL_RUNTIME_PROFILES,
    QWEN25_CODER_COMPLETION_PROFILE, LocalModelDeployment,
    LocalModelDeploymentError, create_local_model_deployment,
)
from skeleton.ai.runtime.inference.llama_cpp import (
    COMPLETION_CHAT_FLAGS, QWEN3_COMPLETION_CHAT_TEMPLATE, LlamaCppModel,
)
from skeleton.ai.runtime.inference.local import LocalInferenceRequest


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


@pytest.mark.parametrize("profile,args,native_profile", [
    ("raw", (), None),
    ("llama-completion-chat", COMPLETION_CHAT_FLAGS, None),
    ("qwen3-completion-chat", (*COMPLETION_CHAT_FLAGS, "--chat-template", QWEN3_COMPLETION_CHAT_TEMPLATE),
     "skeleton.chatml.qwen3-closed-think.v1"),
    (QWEN25_CODER_COMPLETION_PROFILE, (*COMPLETION_CHAT_FLAGS, "--chat-template", CODING_COMPLETION_CHAT_TEMPLATE),
     "skeleton.chatml.coding.v1"),
])
def test_canonical_profiles_publish_exact_native_protocol_without_running_a_model(
    tmp_path, profile, args, native_profile,
):
    # A real regular executable and a minimal admitted GGUF header exercise
    # canonical creation/load/profile selection. This is not an inference or
    # quality fixture; no subprocess is started and no trained weights exist.
    model_path = tmp_path / "protocol-fixture.gguf"
    model_path.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0))
    destination = tmp_path / "jeeves.json"
    prepared = create_local_model_deployment(
        destination, executable_path=sys.executable, model_path=model_path,
        model_id="jeeves", runtime_profile=profile, context_size=4096, threads=2,
    )
    loaded = LocalModelDeployment.load(destination)
    assert loaded.model_id == "jeeves" and loaded.manifest_digest == prepared.manifest_digest
    config = loaded.llama_cpp_config()
    assert config.extra_args == args
    assert config.output_framing == ("raw" if profile == "raw" else "llama_completion_eog")
    runtime = LlamaCppModel(config)
    assert runtime._native_chat_profile() == native_profile
    if profile == QWEN25_CODER_COMPLETION_PROFILE:
        rendered = runtime._render_prompt(LocalInferenceRequest(
            prompt="New question", instructions="System policy",
            history=(("user", "First question"), ("assistant", "First answer")),
            max_output_tokens=16,
        ))
        assert rendered == (
            "<|im_start|>system\nSystem policy<|im_end|>\n"
            "<|im_start|>user\nFirst question<|im_end|>\n"
            "<|im_start|>assistant\nFirst answer<|im_end|>\n"
            "<|im_start|>user\nNew question<|im_end|>\n<|im_start|>assistant\n"
        )
        assert "<think>" not in rendered
    prior = destination.read_bytes()
    with pytest.raises(LocalModelDeploymentError, match="already exists"):
        create_local_model_deployment(
            destination, executable_path=sys.executable, model_path=model_path,
            model_id="replacement", runtime_profile=profile,
        )
    assert destination.read_bytes() == prior


def test_jeeves_builder_exposes_and_forwards_explicit_qwen25_coder_profile(tmp_path, monkeypatch):
    observed = []
    monkeypatch.setattr(builder, "create_local_model_deployment",
                        lambda *_a, **kwargs: observed.append(kwargs) or identity())
    monkeypatch.setattr(builder.LocalModelDeployment, "load", lambda *_a: identity())
    assert QWEN25_CODER_COMPLETION_PROFILE in LOCAL_MODEL_RUNTIME_PROFILES
    code = builder.main([
        "--model", str(tmp_path / "model.gguf"), "--executable", str(tmp_path / "llama-cli"),
        "--output", str(tmp_path / "jeeves.json"), "--profile", QWEN25_CODER_COMPLETION_PROFILE,
    ])
    assert code == 0
    assert observed[0]["runtime_profile"] == QWEN25_CODER_COMPLETION_PROFILE
    assert observed[0]["model_id"] == "jeeves"
