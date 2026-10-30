"""Explicit, device-local Apple Metal/KV qualification of a pinned GGUF.

Runs only on operator-owned Apple Silicon. Does not install a model, download
weights, change macOS swap, or make unsupported GPU-coherence claims.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import threading
from typing import Any

from skeleton.ai.runtime.inference.deployment import LocalModelDeployment
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from .offline_metal_runtime import _apple_silicon
from .offline_resource_fabric import probe_gpu_resources


def evaluate_host_kv_qualification(
    *,
    pinned_manifest_digest: str,
    runtime_digest: str,
    model_digest: str,
    execution_receipt: str,
    requested_kv_location: str,
    selected_gpu_layers: int | None,
    observed: dict[str, Any] | None,
    metal_present: bool,
) -> dict[str, Any]:
    """Return deterministic evidence; unknown or contradictory data is not pass."""
    if any(
        type(value) is not str or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
        for value in (
            pinned_manifest_digest, runtime_digest,
            model_digest, execution_receipt,
        )
    ):
        raise ValueError("pinned qualification requires complete SHA-256 identities")
    reported = bool(
        isinstance(observed, dict) and observed.get("backend_reported") is True
    )
    host_bytes = (
        observed.get("reported_host_kv_bytes", 0)
        if isinstance(observed, dict) else 0
    )
    device_bytes = (
        observed.get("reported_device_kv_bytes", 0)
        if isinstance(observed, dict) else 0
    )
    if any(type(item) is not int or item < 0 for item in (host_bytes, device_bytes)):
        raise ValueError("invalid native memory observations")
    accepted = bool(
        _apple_silicon() and metal_present and requested_kv_location == "host"
        and type(selected_gpu_layers) is int and selected_gpu_layers > 0
        and reported and host_bytes > 0 and device_bytes == 0
    )
    result = {
        "schema": "skeleton.local.metal-kv-device-qualification.v1",
        "status": "qualified_host_kv_diagnostic" if accepted else "unqualified",
        "qualification_accepted": accepted,
        "manifest_sha256": pinned_manifest_digest,
        "runtime_sha256": runtime_digest,
        "model_sha256": model_digest,
        "execution_receipt_sha256": execution_receipt,
        "selected_gpu_layers": selected_gpu_layers,
        "requested_kv_location": requested_kv_location,
        "backend_reported_host_kv_bytes": host_bytes,
        "backend_reported_device_kv_bytes": device_bytes,
        "backend_report_present": reported,
        "metal_telemetry_present": metal_present,
        "driver_coherency_verified": False,
        "device_tensor_migration_verified": False,
        "metal_event_fence_verified": False,
    }
    result["qualification_receipt_sha256"] = sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return result


def qualify_pinned_apple_host_kv(manifest: str | Path) -> dict[str, Any]:
    """Run one private request; never mark device verification without telemetry."""
    if not _apple_silicon():
        raise RuntimeError("Apple Silicon M-series hardware is required")
    deployment = LocalModelDeployment.load(manifest)
    if deployment.kv_cache_location != "host" or not (
        deployment.gpu_layers and deployment.gpu_layers > 0
    ):
        raise RuntimeError(
            "operator must pin host KV and positive GPU layers in the deployment"
        )
    # This is the same locally pinned loader used by offline desktop chat.
    from .local_ai import load_gguf_deployment

    model = load_gguf_deployment(manifest)
    native = model.infer(
        LocalInferenceRequest(
            prompt="Respond with the single word OK.",
            max_output_tokens=8,
        ),
        threading.Event(),
    )
    if not native.execution_receipt_digest:
        raise RuntimeError("native execution returned no pinned receipt")
    return evaluate_host_kv_qualification(
        pinned_manifest_digest=deployment.manifest_digest,
        runtime_digest=model.runtime_digest,
        model_digest=model.model_digest,
        execution_receipt=native.execution_receipt_digest,
        requested_kv_location=model.config.kv_cache_location,
        selected_gpu_layers=model.config.gpu_layers,
        observed=model._last_kv_observation,
        metal_present=any(
            device.vendor == "apple" and device.shared_with_system_ram
            for device in probe_gpu_resources()
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify pinned native Apple Metal/host-KV behavior locally"
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to an existing identity-checked private GGUF deployment",
    )
    args = parser.parse_args()
    try:
        report = qualify_pinned_apple_host_kv(args.manifest)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({
            "schema": "skeleton.local.metal-kv-device-qualification.v1",
            "status": "unqualified", "qualification_accepted": False,
            "reason": type(exc).__name__,
        }, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report["qualification_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
