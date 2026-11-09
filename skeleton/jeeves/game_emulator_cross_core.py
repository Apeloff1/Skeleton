"""Cross-core differential replay analysis for operator-approved libretro libraries.

Uses real isolated workers and identical operator-owned legal inputs. Exact
frame/audio equality is *not* a correctness oracle when cores may choose
different pixel scales, display filters or hardware timing. No training or
automatic score/promotion is performed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence

from .game_emulator_qualification import run_emulator_qualification

SCHEMA = "skeleton.game.emulator_cross_core_audit.v1"
MAX_CORES = 8
MAX_COMBINED_REQUESTED_FRAMES = 65536


class EmulatorCrossCoreError(ValueError):
    """Core comparison request lacks a finite, equal-content input contract."""


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def compare_native_emulator_cores(
    target_id: str,
    *,
    core_ids: Sequence[str],
    expected_registry_digest: str,
    actions: Sequence[str] | None = None,
    controller_tape: Sequence[Sequence[Mapping[str, object]]] | None = None,
    rom_source: bytes | None = None,
    content: object | None = None,
    filename: str = "game.bin",
    reader: Callable | None = None,
    runs_per_core: int = 2,
    seed: int = 0,
    frames_per_step: int = 1,
    controller_devices: Sequence[str] | None = None,
    timeout_seconds: float = 5,
    rights_evidence_digest: str | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Replay identical tape against 2–8 distinct approved native core IDs."""
    if (not isinstance(core_ids, (tuple, list))
        or not 2 <= len(core_ids) <= MAX_CORES
        or len(core_ids) != len(set(core_ids))
        or any(type(identity) is not str or not 1 <= len(identity) <= 80 for identity in core_ids)):
        raise EmulatorCrossCoreError("Select two through eight distinct pinned libretro core IDs")
    if (actions is None) == (controller_tape is None):
        raise EmulatorCrossCoreError("Supply either policy actions or exact raw controller frames")
    tape = actions if actions is not None else controller_tape
    if not isinstance(tape, (list, tuple)) or not 1 <= len(tape) <= 64:
        raise EmulatorCrossCoreError("All cores must use the same bounded 1–64 step action tape")
    if (type(frames_per_step) is not int or not 1 <= frames_per_step <= 8
        or type(runs_per_core) is not int or not 2 <= runs_per_core <= 10
        or len(core_ids) * runs_per_core * (len(tape) * frames_per_step + 32)
            > MAX_COMBINED_REQUESTED_FRAMES):
        raise EmulatorCrossCoreError("Combined per-core reset and step frame budget exceeds 65,536")
    summaries: list[dict[str, object]] = []
    for core_id in core_ids:
        if cancelled is not None and cancelled():
            raise EmulatorCrossCoreError("Operator cancelled the cross-core qualification")
        report = run_emulator_qualification(
            target_id,
            core_id=core_id,
            expected_registry_digest=expected_registry_digest,
            actions=actions,
            controller_tape=controller_tape,
            rom_source=rom_source,
            content=content,
            filename=filename,
            reader=reader,
            runs=runs_per_core,
            seed=seed,
            frames_per_step=frames_per_step,
            controller_devices=controller_devices,
            timeout_seconds=timeout_seconds,
            rights_evidence_digest=rights_evidence_digest,
            include_traces=False,
            cancelled=cancelled,
        )
        summaries.append({
            "core_id": core_id,
            "qualification_sha256": report["qualification_digest"],
            "within_core_replay_status": report["status"],
            "replay_first_divergent_step": report["mirror_audit"]["first_divergent_step"],
            "final_video_sha256_by_run": [
                row["last_video_sha256"] for row in report["run_receipts"]
            ],
            "final_audio_sha256_by_run": [
                row["last_audio_sha256"] for row in report["run_receipts"]
            ],
            "native_run_count": report["runs_completed"],
        })
    pairwise = []
    for index, left in enumerate(summaries):
        for right in summaries[index + 1:]:
            video = left["final_video_sha256_by_run"] == right["final_video_sha256_by_run"]
            audio = left["final_audio_sha256_by_run"] == right["final_audio_sha256_by_run"]
            pairwise.append({
                "core_a": left["core_id"],
                "core_b": right["core_id"],
                "same_exact_final_video_hashes": video,
                "same_exact_final_audio_hashes": audio,
                "same_final_av_hashes": video and audio,
                "accuracy_winner": None,
                "note": "Different output formats or emulation timing are not automatically an accuracy defect",
            })
    report = {
        "schema_version": SCHEMA,
        "status": "cross_core_differential_receipts_collected",
        "target_id": target_id,
        "approved_registry_sha256": expected_registry_digest,
        "input_tape_sha256": _digest(tape),
        "input_kind": "policy_actions" if actions is not None else "multi_port_raw",
        "core_count": len(core_ids),
        "native_runs_per_core": runs_per_core,
        "total_completed_fresh_native_runs": len(core_ids) * runs_per_core,
        "cores": summaries,
        "pairwise_differences": pairwise,
        "distinctions": "Exact matching/differing audiovisual hashes are evidence, not an authoritative golden reference",
        "legal_rom_rights_verified": False,
        "native_hardware_accuracy_proven": False,
        "training_weight_gain_measured": False,
        "model_weights_promoted": False,
    }
    report["cross_core_digest"] = _digest(report)
    return report
