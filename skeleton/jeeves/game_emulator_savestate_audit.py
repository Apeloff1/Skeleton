"""Actual libretro savestate round-trip audit without restarting the native worker.

Uses approved ROM/core/content and real retro_serialize/retro_unserialize.
It never invokes reverse CPU instruction execution, certifies game correctness,
acquires copyrighted sources, or changes model weights.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence

SCHEMA = "skeleton.game.emulator_savestate_roundtrip.v1"


class EmulatorSavestateAuditError(ValueError):
    """A native checkpoint comparison request or result is invalid."""


def _digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def run_native_savestate_roundtrip(
    target_id: str,
    *,
    core_id: str,
    expected_registry_digest: str,
    checkpoint_at: int,
    actions: Sequence[str] | None = None,
    controller_tape: Sequence[Sequence[Mapping[str, object]]] | None = None,
    rom_source: bytes | None = None,
    content: object | None = None,
    filename: str = "game.bin",
    reader: Callable | None = None,
    seed: int = 0,
    frames_per_step: int = 1,
    controller_devices: Sequence[str] | None = None,
    timeout_seconds: float = 5,
    rights_evidence_digest: str | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Compare suffix execution before and after real native serialize/restore.

    Takes exactly one worker, executes a prefix, saves state, executes suffix,
    restores the saved state, then executes that same suffix again. Differences
    in video, audio, observations, reward or transition-chain evidence are
    visible. State-restore behavior is audited, not declared hardware correct.
    """
    from .game_emulator_host import _ACTIONS, _KEY_ACTIONS, _controls, create_emulator_environment

    if (actions is None) == (controller_tape is None):
        raise EmulatorSavestateAuditError("Select one policy or raw controller tape")
    mode = "policy_actions" if actions is not None else "multi_port_raw"
    tape = actions if actions is not None else controller_tape
    if not isinstance(tape, (list, tuple)) or not 2 <= len(tape) <= 64:
        raise EmulatorSavestateAuditError("Checkpoint requires a bounded 2–64 step input tape")
    if type(checkpoint_at) is not int or not 1 <= checkpoint_at < len(tape):
        raise EmulatorSavestateAuditError("Checkpoint index must lie strictly inside the input tape")
    if (type(frames_per_step) is not int or not 1 <= frames_per_step <= 8
        or (len(tape) + len(tape) - checkpoint_at) * frames_per_step + 32 > 2048):
        raise EmulatorSavestateAuditError("Checkpoint replay exceeds 2,048 requested native frames")
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise EmulatorSavestateAuditError("Invalid bounded native episode seed")
    if cancelled is not None and not callable(cancelled):
        raise EmulatorSavestateAuditError("Cancellation probe must be callable")
    if rights_evidence_digest is not None and (
        type(rights_evidence_digest) is not str or len(rights_evidence_digest) != 64
        or any(x not in "0123456789abcdef" for x in rights_evidence_digest)
    ):
        raise EmulatorSavestateAuditError("Legal rights evidence must be an exact SHA-256 reference")
    if actions is not None:
        if any(type(a) is not str or a not in (*_ACTIONS, *_KEY_ACTIONS) for a in actions):
            raise EmulatorSavestateAuditError("A policy input action is outside the declared domain")
        normalized = list(actions)
    else:
        normalized = [_controls(item) for item in controller_tape]
    if (content is None) == (rom_source is None):
        raise EmulatorSavestateAuditError("Provide one exact legally permitted source or content bundle")

    def probe(environment, action):
        if cancelled is not None and cancelled():
            raise EmulatorSavestateAuditError("Operator cancelled native savestate replay")
        step = environment.step(action) if mode == "policy_actions" else environment.input_step(action)
        frame = environment._frame
        return {
            "frame_sha256": frame["pixel_sha256"],
            "audio_sha256": frame["audio_sha256"],
            "audio_frames": frame["audio_frames"],
            "native_runs": frame["runs"],
            "video_callbacks": frame["video_callbacks"],
            "observation": dict(step.observation),
            "reward_components": dict(step.reward_components),
            "transition_digest": step.transition_digest,
        }

    with create_emulator_environment(
        target_id,
        core_id=core_id,
        expected_registry_digest=expected_registry_digest,
        content=content,
        rom_source=rom_source,
        filename=filename,
        reader=reader,
        max_steps=len(normalized),
        frames_per_step=frames_per_step,
        controller_devices=controller_devices,
        timeout_seconds=timeout_seconds,
        cancelled=cancelled,
    ) as environment:
        environment.reset(seed)
        for action in normalized[:checkpoint_at]:
            probe(environment, action)
        snapshot = environment.snapshot()
        original = [probe(environment, action) for action in normalized[checkpoint_at:]]
        environment.restore(snapshot)
        replayed = [probe(environment, action) for action in normalized[checkpoint_at:]]

    comparisons = []
    first_divergence = None
    dimensions = ("frame_sha256", "audio_sha256", "audio_frames",
                  "native_runs", "video_callbacks", "observation",
                  "reward_components", "transition_digest")
    divergence_totals = {key: 0 for key in dimensions}
    for i, (before, after) in enumerate(zip(original, replayed, strict=True), 1):
        differences = [name for name in dimensions if before[name] != after[name]]
        if differences and first_divergence is None:
            first_divergence = i
        for name in differences:
            divergence_totals[name] += 1
        comparisons.append({
            "suffix_step": i,
            "actual_input_sha256": _digest(normalized[checkpoint_at + i - 1]),
            "before_sha256": _digest(before),
            "after_sha256": _digest(after),
            "different_dimensions": differences,
        })
    result: dict[str, object] = {
        "schema_version": SCHEMA,
        "status": "native_state_replay_diverged" if first_divergence is not None
            else "self_reported_native_state_roundtrip_consistent",
        "core_id": core_id,
        "target_id": target_id,
        "source_registry_sha256": expected_registry_digest,
        "mode": mode,
        "input_tape_sha256": _digest(normalized),
        "checkpoint_at_step": checkpoint_at,
        "suffix_steps": len(original),
        "seed": seed,
        "savestate_sha256": snapshot["state_sha256"],
        "snapshot_receipt_sha256": snapshot["snapshot_digest"],
        "first_divergent_suffix_step": first_divergence,
        "divergence_dimension_counts": divergence_totals,
        "comparisons": comparisons,
        "same_native_worker_for_before_and_after": True,
        "source_rom_rights_verified": False,
        "hardware_correctness_verified": False,
        "model_learning_or_weight_promotion": False,
        "semantics": "Restores a libretro checkpoint and retries a suffix, not inverse CPU execution.",
    }
    result["audit_digest"] = _digest(result)
    return result
