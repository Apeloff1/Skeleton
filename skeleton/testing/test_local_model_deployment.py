from __future__ import annotations

from skeleton.testing.local_inference_fixtures import local_serving_resources as local_serving_resources

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
        + struct.pack("<Q", len(b"general.architecture"))
        + b"general.architecture"
        + struct.pack("<I", 8)
        + struct.pack("<Q", len(b"llama"))
        + b"llama"
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


def _deployment_with_adjacent_library(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest, runtime, _ = _deployment(tmp_path)
    library = runtime.parent / "libllama.so.0"
    library.write_bytes(b"pinned runtime library")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runtime_libraries"] = {library.name: _sha(library)}
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest, runtime, library


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Pinned runtime requires no-follow file opens")
def test_adjacent_library_inventory_detects_content_change_before_dispatch(tmp_path: Path) -> None:
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel, LlamaCppRuntimeError
    manifest, _, library = _deployment_with_adjacent_library(tmp_path)
    deployment = LocalModelDeployment.load(manifest)
    backend = LlamaCppModel(deployment.llama_cpp_config())
    assert deployment.runtime_libraries == ((library.name, _sha(library)),)
    before = library.stat()
    library.write_bytes(b"X" * before.st_size)
    os.utime(library, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(LlamaCppRuntimeError, match="library"):
        backend.assert_identity()


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Pinned runtime requires no-follow file opens")
def test_resource_retuning_preserves_deployment_library_pins_and_kv_identity(tmp_path: Path) -> None:
    from dataclasses import replace
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel, LlamaCppRuntimeError

    manifest, _, library = _deployment_with_adjacent_library(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["config"].update(kv_cache_location="backend", kv_cache_type_k="q8_0", kv_cache_type_v="f16")
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    deployment = LocalModelDeployment.load(manifest)
    baseline = deployment.llama_cpp_config()
    backend = LlamaCppModel(baseline)
    assert baseline.runtime_libraries == ((library.name, _sha(library)),)
    assert (baseline.kv_cache_type_k, baseline.kv_cache_type_v) == ("q8_0", "f16")
    for pins in ((), ((library.name, "f" * 64),)):
        with pytest.raises(LlamaCppRuntimeError, match="cannot change model, safety or context identity"):
            backend.activate_prelaunch_resource_profile(replace(baseline, runtime_libraries=pins))
        assert backend.config == baseline
    with pytest.raises(LlamaCppRuntimeError, match="cannot change model, safety or context identity"):
        backend.activate_prelaunch_resource_profile(replace(baseline, kv_cache_type_k="q4_0"))
    backend.activate_prelaunch_resource_profile(replace(
        baseline, threads=1, batch_size=64, kv_cache_location="host",
    ))
    assert backend.config.runtime_libraries == baseline.runtime_libraries
    assert backend.config.kv_cache_location == "host"
    backend.assert_identity()


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Pinned runtime requires no-follow file opens")
@pytest.mark.parametrize("change", ["delete", "add", "symlink", "nested"])
def test_adjacent_library_inventory_rejects_replacement_and_loader_search_changes(tmp_path: Path, change: str) -> None:
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel, LlamaCppRuntimeError
    manifest, runtime, library = _deployment_with_adjacent_library(tmp_path)
    backend = LlamaCppModel(LocalModelDeployment.load(manifest).llama_cpp_config())
    if change == "delete":
        library.unlink()
    elif change == "add":
        (runtime.parent / "libunlisted.so").write_bytes(b"unexpected")
    elif change == "nested":
        (runtime.parent / "glibc-hwcaps").mkdir()
    else:
        if os.name == "nt":
            pytest.skip("Windows symlink creation requires host privileges")
        alternate = tmp_path / "other.so"
        alternate.write_bytes(library.read_bytes())
        library.unlink()
        library.symlink_to(alternate)
    with pytest.raises(LlamaCppRuntimeError, match="runtime"):
        backend.assert_identity()


@pytest.mark.parametrize("name", ["../libevil.so", "/tmp/libevil.so", "libx.so/../escape", "not-a-library"])
def test_adjacent_library_manifest_rejects_unsafe_names(tmp_path: Path, name: str) -> None:
    manifest, _, library = _deployment_with_adjacent_library(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runtime_libraries"] = {name: _sha(library)}
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelDeploymentError, match="invalid llama.cpp deployment config"):
        LocalModelDeployment.load(manifest)


@pytest.mark.parametrize("inventory", [None, {}])
def test_declared_library_inventory_cannot_silently_downgrade_to_legacy(tmp_path: Path, inventory) -> None:
    manifest, _, _ = _deployment_with_adjacent_library(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runtime_libraries"] = inventory
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelDeploymentError, match="non-empty"):
        LocalModelDeployment.load(manifest)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Pinned runtime requires no-follow file opens")
def test_pinned_bundle_strips_ambient_loader_overrides_without_changing_legacy(tmp_path: Path, monkeypatch) -> None:
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig, LlamaCppModel
    manifest, runtime, _ = _deployment_with_adjacent_library(tmp_path)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/untrusted/override")
    monkeypatch.setenv("DYLD_LIBRARY_PATH", "/untrusted/override")
    deployment = LocalModelDeployment.load(manifest)
    strict = LlamaCppModel(deployment.llama_cpp_config())
    assert "LD_LIBRARY_PATH" not in strict._effective_environment()
    assert "DYLD_LIBRARY_PATH" not in strict._effective_environment()
    legacy = LlamaCppModel(LlamaCppConfig(executable=str(runtime), model_path=str(deployment.model_path), context_size=128))
    assert legacy._effective_environment()["LD_LIBRARY_PATH"] == "/untrusted/override"
    for name in ("LD_PRELOAD", "LD_AUDIT", "DYLD_INSERT_LIBRARIES", "GLIBC_TUNABLES", "GGML_BACKEND_PATH"):
        with pytest.raises(ValueError, match="loader environment override"):
            LlamaCppConfig(executable=str(runtime), model_path=str(deployment.model_path),
                           runtime_libraries=deployment.runtime_libraries, environment={name: "override"})


def test_pinned_bundle_refuses_hosts_without_no_follow_open(tmp_path: Path, monkeypatch) -> None:
    manifest, _, _ = _deployment_with_adjacent_library(tmp_path)
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    with pytest.raises(LocalModelDeploymentError, match="library inventory"):
        LocalModelDeployment.load(manifest)


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
    assert runtime.startup_qualification_receipt is not None
    assert runtime.startup_qualification_receipt["status"] == "qualified"
    assert (
        runtime.startup_qualification_receipt["model_sha256"]
        == runtime.local_model.engine.model.model_digest
    )
    assert (
        runtime.startup_qualification_receipt["executable_sha256"]
        == runtime.local_model.runtime_digest
    )


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
    with pytest.raises(LocalModelDeploymentError, match="model_path symlinked path component is forbidden"):
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


def test_sync_qualification_binds_response_to_exact_runtime_and_model(
    tmp_path: Path,
) -> None:
    from skeleton.ai.runtime.inference.deployment import (
        qualify_local_model_deployment_sync,
    )

    manifest, runtime, model = _deployment(tmp_path)
    receipt = qualify_local_model_deployment_sync(
        manifest,
        prompt="qualification identity binding",
        max_output_tokens=8,
    )
    assert _sha(runtime) in receipt["response_id"]
    assert _sha(model) in receipt["response_id"]
    assert receipt["receipt_digest"]


def test_manifest_bootstrap_fails_when_live_qualification_cannot_execute(
    tmp_path: Path,
) -> None:
    manifest, runtime, _ = _deployment(tmp_path)
    runtime.write_text("#!/usr/bin/env python3\nraise SystemExit(7)\n", encoding="utf-8")
    runtime.chmod(0o755)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["executable_sha256"] = _sha(runtime)
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        LocalModelDeploymentError,
        match="qualification execution failed",
    ):
        FunctionalAIRuntime.from_local_model_manifest(
            SQLiteExecutionRepository(),
            manifest,
            AsyncToolRuntime(),
            verification_hook=_verification,
        )

def test_deployment_rejects_model_under_symlinked_parent(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("symlink semantics vary on Windows")
    manifest, _, model = _deployment(tmp_path)
    real_parent=model.parent
    linked_parent=tmp_path/"linked-models"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    payload=json.loads(manifest.read_text(encoding="utf-8"))
    payload["model_path"]="linked-models/agent.gguf"
    manifest.write_text(json.dumps(payload),encoding="utf-8")

    with pytest.raises(
        LocalModelDeploymentError,
        match="symlinked path component is forbidden",
    ):
        LocalModelDeployment.load(manifest)


def test_deployment_rejects_unknown_top_level_manifest_field(tmp_path: Path) -> None:
    manifest, _, _ = _deployment(tmp_path)
    payload=json.loads(manifest.read_text(encoding="utf-8"))
    payload["download_url"]="https://example.invalid/model.gguf"
    manifest.write_text(json.dumps(payload),encoding="utf-8")

    with pytest.raises(
        LocalModelDeploymentError,
        match="unsupported deployment manifest key",
    ):
        LocalModelDeployment.load(manifest)


def test_qualification_rejects_model_id_identity_drift(tmp_path: Path) -> None:
    from skeleton.ai.runtime.inference.deployment import _qualification_receipt
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel
    from skeleton.ai.runtime.inference import LocalInferenceResult

    manifest,_,_= _deployment(tmp_path)
    deployment=LocalModelDeployment.load(manifest)
    model=LlamaCppModel(deployment.llama_cpp_config(rehash_artifacts_each_run=True))
    result=LocalInferenceResult(
        text="offline ready",
        model_id="different-model-id",
        model_digest=deployment.model_sha256,
        input_tokens=2,
        output_tokens=2,
        finish_reason="completed",
        response_id=(
            "local:test:"
            +deployment.executable_sha256
            +":"
            +deployment.model_sha256
        ),
    )

    with pytest.raises(LocalModelDeploymentError,match="model identity drift"):
        _qualification_receipt(
            deployment,
            model,
            result,
            prompt="qualification",
        )


def test_qualification_rejects_truncated_response(tmp_path: Path) -> None:
    from skeleton.ai.runtime.inference.deployment import _qualification_receipt
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel
    from skeleton.ai.runtime.inference import LocalInferenceResult

    manifest,_,_= _deployment(tmp_path)
    deployment=LocalModelDeployment.load(manifest)
    model=LlamaCppModel(deployment.llama_cpp_config(rehash_artifacts_each_run=True))
    result=LocalInferenceResult(
        text="partial readiness",
        model_id=deployment.model_id,
        model_digest=deployment.model_sha256,
        input_tokens=2,
        output_tokens=2,
        finish_reason="length",
        response_id=(
            "local:test:"
            +deployment.executable_sha256
            +":"
            +deployment.model_sha256
        ),
    )

    with pytest.raises(LocalModelDeploymentError,match="did not reach a completed"):
        _qualification_receipt(
            deployment,
            model,
            result,
            prompt="qualification",
        )
