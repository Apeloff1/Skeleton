"""Explicit, device-local Apple Metal/KV qualification of a pinned GGUF.

Runs only on operator-owned Apple Silicon. Does not install a model, download
weights, change macOS swap, or make unsupported GPU-coherence claims.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
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
        observed=model.kv_observation_for_receipt(
            native.execution_receipt_digest
        ),
        metal_present=any(
            device.vendor == "apple" and device.shared_with_system_ram
            for device in probe_gpu_resources()
        ),
    )


def _validated_shared_fence_receipt(data: object) -> dict[str, Any]:
    """Only a complete bounded, schema-checked Metal test is accepted."""
    if not isinstance(data, dict) or set(data) != {
        "schema", "passed", "shared_metal_buffers",
        "synchronized_command_buffers", "verified_values", "output_sha256",
        "model_tensor_fence_verified", "llama_kv_cache_fence_verified",
    }:
        raise RuntimeError("unexpected native Metal fence receipt")
    if (
        data["schema"] != "skeleton.apple.metal-shared-fence.v1"
        or data["passed"] is not True
        or type(data["shared_metal_buffers"]) is not int
        or data["shared_metal_buffers"] != 2
        or type(data["synchronized_command_buffers"]) is not int
        or data["synchronized_command_buffers"] != 2
        or type(data["verified_values"]) is not int
        or data["verified_values"] != 128
        or type(data["output_sha256"]) is not str
        or len(data["output_sha256"]) != 64
        or any(ch not in "0123456789abcdef" for ch in data["output_sha256"])
        or data["model_tensor_fence_verified"] is not False
        or data["llama_kv_cache_fence_verified"] is not False
    ):
        raise RuntimeError("invalid native shared-buffer fence evidence")
    return dict(data)


def qualify_apple_shared_buffer_fence() -> dict[str, Any]:
    """Opt-in real Metal shared buffer test using the installed Apple compiler.

    It is independent of llama.cpp: never use this result to claim model GPU
    allocation, model tensor migration, or model KV synchronization.
    """
    if not _apple_silicon():
        raise RuntimeError("shared Metal fence needs an Apple Silicon Mac")
    source = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "qualify_metal_shared.swift"
    )
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("trusted Metal qualification source unavailable")
    original = source.read_bytes()
    if not original or len(original) > 32_768:
        raise RuntimeError("unbounded native qualification source")
    source_sha = sha256(original).hexdigest()
    if not os.access("/usr/bin/xcrun", os.X_OK):
        raise RuntimeError("Apple xcrun developer tooling unavailable")
    try:
        invocation = subprocess.run(
            ["/usr/bin/xcrun", "swift", str(source)],
            check=False, capture_output=True,
            timeout=180, cwd=str(source.parent),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("native Metal fence invocation failed") from exc
    if sha256(source.read_bytes()).hexdigest() != source_sha:
        raise RuntimeError("Metal qualification source changed while running")
    if invocation.returncode != 0 or len(invocation.stdout) > 8192:
        raise RuntimeError("Metal shared-buffer qualification failed")
    try:
        output = json.loads(invocation.stdout.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError("invalid native Metal fence output") from exc
    result = _validated_shared_fence_receipt(output)
    result["qualification_source_sha256"] = source_sha
    result["model_tensor_fence_verified"] = False
    result["llama_kv_cache_fence_verified"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify pinned native Apple Metal/host-KV behavior locally"
    )
    parser.add_argument(
        "--manifest", required=True,
        help="Path to an existing identity-checked private GGUF deployment",
    )
    parser.add_argument(
        "--shared-buffer-fence", action="store_true",
        help="also exercise independent real Metal shared-buffer synchronization",
    )
    args = parser.parse_args()
    try:
        report = qualify_pinned_apple_host_kv(args.manifest)
        if args.shared_buffer_fence:
            shared = qualify_apple_shared_buffer_fence()
            report["shared_buffer_fence"] = shared
            report["standalone_shared_metal_fence_verified"] = True
            # This qualifies only the standalone shared-buffer experiment.
            # Never infer that llama.cpp KV buffers were synchronized.
            report["driver_coherency_verified"] = False
            report["metal_event_fence_verified"] = False
            report["qualification_receipt_sha256"] = sha256(
                json.dumps(
                    {k: v for k, v in report.items()
                     if k != "qualification_receipt_sha256"},
                    sort_keys=True, separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
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
