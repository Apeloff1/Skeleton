"""Offline model readiness inspection without provider calls or inference.

This is read-only artifact admission evidence. It does not prove OS egress
blocking, answer quality, bundled device libraries or execution qualification.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


SCHEMA = "skeleton.app.offline_readiness.v1"


def inspect_local_readiness(
    *,
    model: str | Path | None = None,
    deployment: str | Path | None = None,
) -> dict[str, Any]:
    if (model is None) == (deployment is None):
        raise ValueError("select exactly one local model or GGUF deployment")

    if model is not None:
        from skeleton.app.local_ai import load_native_checkpoint
        backend = load_native_checkpoint(model)
        backend.assert_identity()
        details = {
            "kind": "native-checkpoint",
            "model_digest": backend.model_digest,
            "runtime_digest": backend.runtime_digest,
            "model_id": getattr(backend, "model_id", "skeleton-native-transformer"),
            "context_tokens": backend.runtime.limits.max_context,
            "max_output_tokens": backend.runtime.limits.max_new_tokens,
            "artifact": "native checkpoint validated",
        }
    else:
        from skeleton.ai.runtime.inference.deployment import LocalModelDeployment
        from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel
        admitted = LocalModelDeployment.load(deployment)
        backend = LlamaCppModel(
            admitted.llama_cpp_config(rehash_artifacts_each_run=True)
        )
        details = {
            "kind": "gguf-llama.cpp",
            "model_id": backend.model_id,
            "model_digest": backend.model_digest,
            "runtime_digest": backend.runtime_digest,
            "context_tokens": admitted.context_size,
            "max_output_tokens": None,
            "artifact": "GGUF and runtime binary SHA-256 validated",
            "gguf_version": backend.gguf_header.version,
            "gguf_tensor_count": backend.gguf_header.tensor_count,
        }
    return {
        "schema_version": SCHEMA,
        "ready": True,
        "network_required_for_inference": False,
        "hosted_provider_credentials_required": False,
        "docker_required_for_inference": False,
        "artifacts_verified": True,
        "generation_executed": False,
        "os_egress_isolation_verified": False,
        "runtime_dependencies_verified": False,
        **details,
    }


__all__ = ["SCHEMA", "inspect_local_readiness"]
