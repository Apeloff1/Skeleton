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
import tempfile
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
    metal_model = (
        observed.get("backend_reported_metal_model_bytes", 0)
        if isinstance(observed, dict) else 0
    )
    offloaded = (
        observed.get("backend_reported_gpu_layers", 0)
        if isinstance(observed, dict) else 0
    )
    unknown = (
        observed.get("unrecognized_allocation_lines", 0)
        if isinstance(observed, dict) else 0
    )
    if any(type(item) is not int or item < 0
           for item in (host_bytes, device_bytes, metal_model, offloaded, unknown)):
        raise ValueError("invalid native memory observations")
    accepted = bool(
        _apple_silicon() and metal_present and requested_kv_location == "host"
        and type(selected_gpu_layers) is int and selected_gpu_layers > 0
        and reported and host_bytes > 0 and device_bytes == 0
        and metal_model > 0 and 0 < offloaded <= selected_gpu_layers + 1
        and unknown == 0
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
        "unrecognized_native_kv_lines": unknown,
        "backend_reported_metal_model_bytes": metal_model,
        "backend_reported_gpu_layers": offloaded,
        "offload_count_consistent_with_request": (
            type(selected_gpu_layers) is int
            and 0 < offloaded <= selected_gpu_layers + 1
        ),
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


def _expected_multisync_digest() -> str:
    """Independent CPU calculation of all four fixed Swift GPU workloads."""
    digest = sha256()
    phases = (
        (range(4), 1),
        (range(100, 104), 2),
        (range(200, 203), 1),
        (range(300, 302), 1),
    )
    for seeds, transformations in phases:
        for seed in seeds:
            for index in range(64):
                value = seed * 100_003 + index * 97
                for _ in range(transformations):
                    value = ((value ^ 0x5a17b3e2) + index) & 0xffffffff
                digest.update(value.to_bytes(4, "little"))
    return digest.hexdigest()


def _validated_shared_fence_receipt(data: object) -> dict[str, Any]:
    """Accept only the complete four-mode native Metal synchronization probe.

    Evidence is strictly for the allocated probe buffers. A standalone
    shared-event completion cannot certify llama.cpp's memory allocator.
    """
    if not isinstance(data, dict) or set(data) != {
        "schema", "passed", "shared_metal_buffers",
        "synchronized_command_buffers", "verified_values",
        "serial_cpu_gpu_cpu_round_trips", "cross_queue_event_handoffs",
        "parallel_independent_lanes", "shared_event_cpu_observations",
        "shared_event_cpu_acknowledgements", "output_sha256", "model_tensor_fence_verified",
        "llama_kv_cache_fence_verified",
    }:
        raise RuntimeError("unexpected native multi-sync Metal receipt")
    expected_counts = {
        "shared_metal_buffers": 13,
        "synchronized_command_buffers": 17,
        "verified_values": 832,
        "serial_cpu_gpu_cpu_round_trips": 4,
        "cross_queue_event_handoffs": 4,
        "parallel_independent_lanes": 3,
        "shared_event_cpu_observations": 2,
        "shared_event_cpu_acknowledgements": 2,
    }
    if (
        data["schema"] != "skeleton.apple.metal-multisync.v2"
        or data["passed"] is not True
        or any(type(data[key]) is not int or data[key] != expected
               for key, expected in expected_counts.items())
        or type(data["output_sha256"]) is not str
        or data["output_sha256"] != _expected_multisync_digest()
        or data["model_tensor_fence_verified"] is not False
        or data["llama_kv_cache_fence_verified"] is not False
    ):
        raise RuntimeError("invalid native multi-sync Metal evidence")
    return dict(data)


def qualify_apple_shared_buffer_fence() -> dict[str, Any]:
    """Opt-in four-mode real Metal synchronization test on Apple hardware.

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
        with tempfile.TemporaryFile(mode="w+b") as output_file:
            invocation = subprocess.run(
                ["/usr/bin/xcrun", "swift", str(source)],
                check=False, stdout=output_file,
                stderr=subprocess.DEVNULL,
                timeout=180, cwd=str(source.parent),
            )
            output_file.seek(0)
            bounded_stdout = output_file.read(8193)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("native Metal fence invocation failed") from exc
    if sha256(source.read_bytes()).hexdigest() != source_sha:
        raise RuntimeError("Metal qualification source changed while running")
    if invocation.returncode != 0 or len(bounded_stdout) > 8192:
        raise RuntimeError("Metal shared-buffer qualification failed")
    try:
        output = json.loads(bounded_stdout.decode("utf-8", errors="strict"))
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
