from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct

import pytest

from skeleton.ai.runtime.functional_ai import FunctionalAIRuntime
from skeleton.ai.runtime.inference.deployment import (
    LocalModelDeployment,
    LocalModelDeploymentError,
    load_local_model_adapter,
    qualify_local_model_deployment,
)
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import ProviderRequest
from skeleton.skills.tool_runtime import AsyncToolRuntime


_RUNTIME = r'''#!/usr/bin/env python3
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("-m")
parser.add_argument("-f")
parser.add_argument("-n")
parser.add_argument("--seed")
parser.add_argument("--temp")
args, unknown = parser.parse_known_args()
prompt = Path(args.f).read_text(encoding="utf-8")
if "qualification" in prompt.lower():
    print("offline model ready")
else:
    print("manifest-loaded local answer")
'''


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deployment(tmp_path: Path) -> tuple[Path, Path, Path]:
    runtime = tmp_path / "bin" / "llama-cli"
    runtime.parent.mkdir()
    runtime.write_text(_RUNTIME, encoding="utf-8")
    runtime.chmod(0o755)
    model = tmp_path / "models" / "agent.gguf"
    model.parent.mkdir()
    model.write_bytes(
        struct.pack("<4sIQQ", b"GGUF", 3, 2, 1)
        + b"operator-owned-model-v1"
    )
    manifest = tmp_path / "deployment.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "skeleton.local_model.deployment.v1",
                "runtime_kind": "llama.cpp-cli",
                "model_id": "operator-agent-v1",
                "executable_path": "bin/llama-cli",
                "executable_sha256": _sha(runtime),
                "model_path": "models/agent.gguf",
                "model_sha256": _sha(model),
                "config": {
                    "timeout_seconds": 5.0,
                    "max_output_bytes": 16384,
                    "max_stderr_bytes": 8192,
                    "context_size": 2048,
                    "threads": 2,
                    "batch_size": 128,
                    "gpu_layers": 0,
                    "temperature": 0.0,
                    "extra_args": [],
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest, runtime, model


def _verification(_request, candidate: str, context_digest: str) -> ExecutionVerificationDecision:
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "deployment-test",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:deployment-test",),
    )


def test_deployment_manifest_binds_relative_artifacts_and_hashes(tmp_path: Path) -> None:
    manifest, runtime, model = _deployment(tmp_path)
    deployment = LocalModelDeployment.load(manifest)
    assert deployment.runtime_kind == "llama.cpp-cli"
    assert deployment.model_id == "operator-agent-v1"
    assert deployment.executable_path == runtime.resolve()
    assert deployment.model_path == model.resolve()
    assert deployment.executable_sha256 == _sha(runtime)
    assert deployment.model_sha256 == _sha(model)
    assert deployment.context_size == 2048
    assert deployment.gguf_version == 3
    assert deployment.gguf_tensor_count == 2
    assert deployment.gguf_metadata_count == 1


@pytest.mark.asyncio
async def test_manifest_loads_directly_into_provider_neutral_adapter(tmp_path: Path) -> None:
    manifest, _, _ = _deployment(tmp_path)
    adapter = load_local_model_adapter(manifest)
    response = await adapter.generate(
        ProviderRequest(
            instructions="Answer locally.",
            prompt="Use the configured standalone model.",
            max_output_tokens=8,
        )
    )
    assert response.provider == "local"
    assert response.model == "operator-agent-v1"
    assert response.text == "manifest-loaded local answer"
    assert response.usage.billed_cost == "0"


def test_functional_runtime_bootstraps_from_local_model_manifest(tmp_path: Path) -> None:
    manifest, _, _ = _deployment(tmp_path)
    runtime = FunctionalAIRuntime.from_local_model_manifest(
        SQLiteExecutionRepository(),
        manifest,
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    assert runtime.local_model.provider_id == "local"
    assert runtime.local_model.model == "operator-agent-v1"


@pytest.mark.asyncio
async def test_qualification_receipt_exposes_hashes_not_raw_prompt(tmp_path: Path) -> None:
    manifest, runtime, model = _deployment(tmp_path)
    prompt = "qualification secret probe text"
    receipt = await qualify_local_model_deployment(
        manifest,
        prompt=prompt,
        max_output_tokens=8,
    )
    assert receipt["status"] == "qualified"
    assert receipt["provider"] == "local"
    assert receipt["network_required"] is False
    assert receipt["hosted_provider_credentials_required"] is False
    assert receipt["model_sha256"] == _sha(model)
    assert receipt["executable_sha256"] == _sha(runtime)
    assert receipt["gguf_version"] == 3
    assert receipt["gguf_tensor_count"] == 2
    assert receipt["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert prompt not in json.dumps(receipt)


def test_deployment_rejects_manifest_model_digest_mismatch(tmp_path: Path) -> None:
    manifest, _, _ = _deployment(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["model_sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelDeploymentError, match="model artifact digest mismatch"):
        LocalModelDeployment.load(manifest)


def test_deployment_rejects_runtime_digest_mismatch(tmp_path: Path) -> None:
    manifest, _, _ = _deployment(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["executable_sha256"] = "f" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelDeploymentError, match="runtime executable digest mismatch"):
        LocalModelDeployment.load(manifest)


def test_deployment_rejects_artifact_mutation_after_manifest(tmp_path: Path) -> None:
    manifest, _, model = _deployment(tmp_path)
    model.write_bytes(b"GGUF-mutated-after-signoff")
    with pytest.raises(LocalModelDeploymentError, match="model artifact digest mismatch"):
        LocalModelDeployment.load(manifest)


def test_deployment_rejects_model_symlink(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("symlink semantics vary on Windows")
    manifest, _, model = _deployment(tmp_path)
    linked = tmp_path / "models" / "linked.gguf"
    linked.symlink_to(model)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["model_path"] = "models/linked.gguf"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelDeploymentError, match="model_path symlink is forbidden"):
        LocalModelDeployment.load(manifest)


def test_deployment_rejects_unknown_config_keys(tmp_path: Path) -> None:
    manifest, _, _ = _deployment(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["config"]["download_url"] = "https://example.invalid/model.gguf"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelDeploymentError, match="unsupported deployment config key"):
        LocalModelDeployment.load(manifest)


def test_deployment_rejects_runtime_kind_drift(tmp_path: Path) -> None:
    manifest, _, _ = _deployment(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runtime_kind"] = "hosted-provider"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelDeploymentError, match="runtime_kind must be llama.cpp-cli"):
        LocalModelDeployment.load(manifest)


def test_deployment_rejects_digest_pinned_non_gguf_artifact(tmp_path: Path) -> None:
    manifest, _, model = _deployment(tmp_path)
    model.write_bytes(b"arbitrary-binary-that-is-not-gguf")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["model_sha256"] = _sha(model)
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelDeploymentError, match="GGUF"):
        LocalModelDeployment.load(manifest)
