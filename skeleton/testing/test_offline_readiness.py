"""Offline readiness receipts distinguish artifact admission from real execution."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import hashlib
import os

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.offline_cli import main
from skeleton.app.offline_readiness import SCHEMA, inspect_local_readiness
from skeleton.cortex.transformer import TinyTransformer


def _model(path: Path) -> Path:
    runtime = NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "answer"),
        dim=8, ctx=64, seed=41, n_heads=2, n_layers=2, d_ff=16,
    ))
    write_local_model_artifact(NativeRuntimeLocalModel(runtime), path)
    return path


def test_native_readiness_is_explicitly_not_generation_or_os_isolation(
    tmp_path: Path,
) -> None:
    report = inspect_local_readiness(model=_model(tmp_path / "native.json"))
    assert report["schema_version"] == SCHEMA
    assert report["kind"] == "native-checkpoint"
    assert report["ready"] is True
    assert report["artifacts_verified"] is True
    assert report["generation_executed"] is False
    assert report["os_egress_isolation_verified"] is False
    assert report["runtime_dependencies_verified"] is False
    assert len(report["model_digest"]) == 64
    assert len(report["runtime_digest"]) == 64


def test_frozen_console_doctor_reports_valid_artifact_without_inference(
    tmp_path: Path, capsys,
) -> None:
    source = _model(tmp_path / "checkpoint.json")
    assert main(["--model", str(source), "--doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["kind"] == "native-checkpoint"
    assert report["generation_executed"] is False


def test_invalid_artifacts_do_not_return_false_readiness(tmp_path: Path, capsys) -> None:
    with pytest.raises((OSError, ValueError, RuntimeError)):
        inspect_local_readiness(model=tmp_path / "absent.json")
    assert main(["--doctor", "--model", str(tmp_path / "absent.json")]) == 1
    assert "rejected" in capsys.readouterr().err
    assert main(["--doctor", "--model", "x", "--prompt", "hello"]) == 2


def test_gguf_readiness_binds_binary_and_weights(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX executable fixture")
    exe = tmp_path / "llama-cli"
    exe.write_text("#!/bin/sh\necho local\n", encoding="utf-8")
    exe.chmod(0o755)
    weights = tmp_path / "model.gguf"
    weights.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 2, 0) + b"demo-weights")
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = tmp_path / "deployment.json"
    manifest.write_text(json.dumps({
        "schema_version": "skeleton.local_model.deployment.v1",
        "runtime_kind": "llama.cpp-cli",
        "model_id": "offline-test",
        "executable_path": "llama-cli",
        "executable_sha256": sha(exe),
        "model_path": "model.gguf",
        "model_sha256": sha(weights),
        "config": {"context_size": 2048},
    }), encoding="utf-8")
    report = inspect_local_readiness(deployment=manifest)
    assert report["kind"] == "gguf-llama.cpp"
    assert report["gguf_version"] == 3
    assert report["model_digest"] == sha(weights)
    assert report["runtime_digest"] == sha(exe)
    weights.write_bytes(weights.read_bytes() + b"tamper")
    with pytest.raises((ValueError, RuntimeError), match="digest"):
        inspect_local_readiness(deployment=manifest)
