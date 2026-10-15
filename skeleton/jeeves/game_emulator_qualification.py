"""Bounded active replay qualification against operator-approved native libretro cores.

This runner creates a new sandboxed emulator process per pass and replays a
fixed, explicit action tape. It compares actual captured frame/audio evidence.
It does not certify intellectual-property rights, hardware compatibility,
gameplay success or a production model weight update.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .game_emulator_replay_audit import compare_emulator_replays

SCHEMA = "skeleton.game.native_emulator_qualification.v1"
MAX_REPLAY_RUNS = 10
MAX_ACTIONS = 64
MAX_FRAME_BUDGET = 4096
MAX_EXPORT_BYTES = 8 * 1024 * 1024


class EmulatorQualificationError(ValueError):
    """A requested native emulator qualification exceeds its exact bounds."""


def run_emulator_qualification(
    target_id: str,
    *,
    core_id: str,
    expected_registry_digest: str,
    actions: Sequence[str],
    content: object | None = None,
    rom_source: bytes | None = None,
    filename: str = "game.bin",
    reader: Callable | None = None,
    runs: int = 3,
    seed: int = 0,
    frames_per_step: int = 1,
    controller_devices: Sequence[str] | None = None,
    timeout_seconds: float = 5.0,
    rights_evidence_digest: str | None = None,
    include_traces: bool = False,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Execute 2–10 actual fresh native workers and compare exact replay evidence.

    The selected core must already be approved by the operator; no source
    fetching, compilation, BIOS acquisition, mock or reference-game fallback.
    The same caller-owned content descriptor is pinned separately per run.
    """
    if (type(target_id) is not str or not target_id
        or type(core_id) is not str or not core_id
        or type(expected_registry_digest) is not str
        or len(expected_registry_digest) != 64
        or any(char not in "0123456789abcdef" for char in expected_registry_digest)):
        raise EmulatorQualificationError("Explicit canonical core, target and registry digest are required")
    if type(runs) is not int or not 2 <= runs <= MAX_REPLAY_RUNS:
        raise EmulatorQualificationError("Native mirror pass count must be 2 through 10")
    if (not isinstance(actions, (list, tuple))
        or not 1 <= len(actions) <= MAX_ACTIONS
        or any(type(action) is not str for action in actions)):
        raise EmulatorQualificationError("Exact policy action tape must contain 1 through 64 finite strings")
    if (type(frames_per_step) is not int or not 1 <= frames_per_step <= 8
        or (frames_per_step * len(actions) + 32) * runs > MAX_FRAME_BUDGET):
        raise EmulatorQualificationError("Total native frame budget exceeds its 4,096-frame hard bound")
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise EmulatorQualificationError("Native replay seed is not a bounded episode label")
    if type(include_traces) is not bool:
        raise EmulatorQualificationError("Full trace export admission must be a boolean")
    if (content is None) == (rom_source is None):
        raise EmulatorQualificationError("Select exactly one lawful core content source")
    if cancelled is not None and not callable(cancelled):
        raise EmulatorQualificationError("Cancellation probe is not callable")
    if rights_evidence_digest is not None and (
        type(rights_evidence_digest) is not str or len(rights_evidence_digest) != 64
        or any(char not in "0123456789abcdef" for char in rights_evidence_digest)
    ):
        raise EmulatorQualificationError("Optional rights evidence requires an exact SHA-256 identity")
    from .game_emulator_host import create_emulator_environment

    traces = []
    run_receipts = []
    for run_index in range(runs):
        if cancelled is not None and cancelled():
            raise EmulatorQualificationError("Native replay qualification was cancelled")
        # A brand-new EmulatorEnvironment launches and subsequently tears down
        # a brand-new bubblewrap-isolated native subprocess on every iteration.
        with create_emulator_environment(
            target_id,
            core_id=core_id,
            expected_registry_digest=expected_registry_digest,
            content=content,
            rom_source=rom_source,
            filename=filename,
            reader=reader,
            max_steps=len(actions),
            frames_per_step=frames_per_step,
            controller_devices=controller_devices,
            timeout_seconds=timeout_seconds,
            cancelled=cancelled,
        ) as environment:
            trace = environment.capture_training_trace(
                actions, seed=seed, rights_evidence_digest=rights_evidence_digest
            )
        traces.append(trace)
        last = trace["transitions"][-1]["info"]
        run_receipts.append({
            "run": run_index + 1,
            "trace_sha256": trace["trace_digest"],
            "capture_nonce": trace["source_lineage"]["capture_nonce"],
            "steps": trace["steps"],
            "native_runs_observed": last["native_runs"],
            "last_video_sha256": last["frame_sha256"],
            "last_audio_sha256": last["audio_sha256"],
            "fresh_worker_process_requested": True,
            "external_execution_attestation": False,
        })
    audit = compare_emulator_replays(traces)
    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "status": "native_replay_disagreement" if audit["status"] == "replay_divergence_detected"
            else "self_reported_native_replay_consistent",
        "core_id": core_id,
        "target_id": target_id,
        "source_registry_sha256": expected_registry_digest,
        "episode_seed": seed,
        "frames_per_step": frames_per_step,
        "requested_native_frames_upper_bound": runs * len(actions) * frames_per_step + runs * 32,
        "runs_requested": runs,
        "runs_completed": len(traces),
        "trace_digests": [row["trace_digest"] for row in traces],
        "run_receipts": run_receipts,
        "mirror_audit": audit,
        "rights_evidence_digest": rights_evidence_digest,
        "rom_rights_legal_reviewed": False,
        "independently_attested": False,
        "hardware_compatibility_verified": False,
        "gameplay_success_verified": False,
        "model_weights_modified": False,
        "production_training_promoted": False,
        "training_utility": "native observations and self-reported replay consistency, not a measure of AI improvement",
    }
    if include_traces:
        encoded = json.dumps(traces, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(encoded) > MAX_EXPORT_BYTES:
            raise EmulatorQualificationError("Combined offline native trace export exceeds 8 MiB")
        report["traces"] = traces
    report["qualification_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return report
