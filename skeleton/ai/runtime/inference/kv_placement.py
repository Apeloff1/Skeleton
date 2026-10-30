"""Bounded, non-attested llama.cpp KV residency diagnostics.

A native backend owns Metal buffers. These parsed startup diagnostics are
evidence of what that backend *reported*, not a driver-level proof of
synchronization, DMA, unified-memory residency or GPU cache coherence.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any


# Only native llama.cpp KV allocation lines, never free-form model output.
_KV_LINE = re.compile(
    r"^\s*llama_kv_cache(?:_unified)?\s*:\s*"
    r"(?P<device>CPU|Metal[0-9]*|CUDA[0-9]*|ROCm[0-9]*|Vulkan[0-9]*)"
    r"\s+KV buffer size\s*=\s*"
    r"(?P<size>[0-9]{1,10}(?:\.[0-9]{1,3})?)"
    r"\s*(?P<unit>KiB|MiB|GiB)\s*$",
    re.IGNORECASE,
)
_MULTIPLIERS = {"kib": 1024, "mib": 1024**2, "gib": 1024**3}
_GPU_LAYER_SUMMARY = re.compile(
    r"^\s*llama_model_load\s*:\s*offloaded\s+"
    r"(?P<actual>[0-9]{1,4})/(?P<total>[0-9]{1,4})"
    r"\s+layers\s+to\s+GPU\s*$",
    re.IGNORECASE,
)
_METAL_MODEL_BUFFER = re.compile(
    r"^\s*llama_model_load\s*:\s*Metal[0-9]*\s+model buffer size\s*=\s*"
    r"(?P<size>[0-9]{1,10}(?:\.[0-9]{1,3})?)"
    r"\s*(?P<unit>KiB|MiB|GiB)\s*$",
    re.IGNORECASE,
)


def observe_native_kv_placement(stderr: bytes) -> dict[str, Any]:
    """Parse only conservative bounded launcher reports.

    Missing log entries mean unknown. Malformed, contradictory or oversized
    diagnostic values are not turned into assertions of residency.
    """
    if type(stderr) is not bytes or len(stderr) > 16 * 1024 * 1024:
        raise ValueError("native diagnostic input must be bounded bytes")
    host = 0
    gpu = 0
    rows = 0
    offloaded_gpu_layers = 0
    metal_model_bytes = 0
    unknown_allocation_lines = 0
    seen: set[tuple[str, str, str]] = set()
    for line in stderr.decode("utf-8", errors="replace").splitlines():
        if len(line) > 512:
            continue
        offloaded = _GPU_LAYER_SUMMARY.fullmatch(line)
        if offloaded is not None:
            actual = int(offloaded["actual"])
            total = int(offloaded["total"])
            if 0 < actual <= total:
                offloaded_gpu_layers = max(offloaded_gpu_layers, actual)
        metal_model = _METAL_MODEL_BUFFER.fullmatch(line)
        if metal_model is not None:
            units = metal_model["unit"].lower()
            number = metal_model["size"].split(".")
            scaled = int(number[0]) * 1000
            if len(number) > 1:
                scaled += int(number[1].ljust(3, "0"))
            byte_count = scaled * _MULTIPLIERS[units] // 1000
            if 0 < byte_count <= 1 << 50:
                metal_model_bytes = max(metal_model_bytes, byte_count)
        match = _KV_LINE.fullmatch(line)
        if match is None:
            # A native KV allocation line with an unsupported device,
            # precision or size cannot be treated as proof of zero GPU KV.
            if ("KV buffer size" in line and
                    ("llama_kv_cache:" in line
                     or "llama_kv_cache_unified:" in line)):
                unknown_allocation_lines += 1
            continue
        groups = match.groupdict()
        identity = (
            groups["device"].lower(), groups["size"], groups["unit"].lower(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        # Thousandths precision only; avoid floating point/overflow.
        digits = groups["size"].split(".")
        numerator = int(digits[0]) * 1000
        if len(digits) == 2:
            numerator += int(digits[1].ljust(3, "0"))
        amount = (
            numerator * _MULTIPLIERS[groups["unit"].lower()] // 1000
        )
        if not 0 < amount <= 1 << 50:
            unknown_allocation_lines += 1
            continue
        if groups["device"].casefold() == "cpu":
            host += amount
        else:
            gpu += amount
        rows += 1
    # Hash only the raw bounded log; no token, source path or prompt content
    # is copied into a telemetry result or durable receipt.
    return {
        "schema": "skeleton.llama-cpp.kv-observation.v1",
        "evidence_type": "backend_diagnostic_not_driver_attestation",
        "native_stderr_sha256": sha256(stderr).hexdigest(),
        "reported_host_kv_bytes": host,
        "reported_device_kv_bytes": gpu,
        "backend_reported_metal_model_bytes": metal_model_bytes,
        "backend_reported_gpu_layers": offloaded_gpu_layers,
        "matched_allocation_lines": rows,
        "unrecognized_allocation_lines": unknown_allocation_lines,
        "backend_reported": bool(rows),
        "actual_gpu_coherency_proven": False,
        "native_sync_fence_proven": False,
    }


__all__ = ["observe_native_kv_placement"]
