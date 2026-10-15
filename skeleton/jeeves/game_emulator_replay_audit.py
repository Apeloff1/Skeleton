"""Read-only replay consistency audit for actual, hash-chained Jeeves libretro episodes.

This module compares native evidence from the existing canonical offline trace
validator. It never launches a core, fetches a ROM, certifies rights, learns model
weights, or mistakes deterministic audiovisual output for successful gameplay.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence

from .game_learning_ingestion import _validate_trace

SCHEMA = "skeleton.game.emulator_replay_audit.v1"
MAX_REPEATS = 10
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_REQUIRED_LINEAGE = {
    "core_id", "core_sha256", "content_digest", "registry_digest",
    "firmware_digest", "options_digest", "source_code_digest",
    "frames_per_step", "capture_nonce", "runtime_kind",
    "production_training_admitted", "rights_verified",
    "hardware_compatibility_verified", "game_success_verified",
}
_REQUIRED_STEP_INFO = {
    "runtime_kind", "source", "frame_sha256", "audio_sha256",
    "controls_sha256", "previous_transition_digest",
    "native_runs", "video_callbacks", "audio_frames",
}
_DIMENSIONS = (
    "video", "audio", "observation", "reward",
    "transition_chain", "native_callbacks",
)


class EmulatorReplayAuditError(ValueError):
    """A native trace cannot be compared under the immutable replay contract."""


def _failure(reason: str) -> None:
    raise EmulatorReplayAuditError(reason)


def _identity(value: object, pattern: re.Pattern[str], description: str) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _failure(description + " must be a canonical lowercase hex identity")
    return value


def _validated_native_trace(raw: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(raw, dict):
        _failure("A canonical offline trace object is required")
    trace = _validate_trace(raw)
    lineage = trace["source_lineage"]
    if not _REQUIRED_LINEAGE <= set(lineage):
        _failure("Native episode lineage is missing immutable source and capture receipts")
    if (lineage["runtime_kind"] != "installed_libretro_emulator"
        or lineage["rights_verified"] is not False
        or lineage["hardware_compatibility_verified"] is not False
        or lineage["game_success_verified"] is not False
        or lineage["production_training_admitted"] is not False):
        _failure("The replay audit only accepts unpromoted native source evidence")
    _identity(lineage["capture_nonce"], _NONCE, "Capture receipt")
    for name in ("core_sha256", "content_digest", "registry_digest",
                 "firmware_digest", "options_digest", "source_code_digest"):
        _identity(lineage[name], _DIGEST, name)
    if type(lineage["frames_per_step"]) is not int or not 1 <= lineage["frames_per_step"] <= 60:
        _failure("Native frame cadence is invalid")
    for transition in trace["transitions"]:
        info = transition.get("info")
        if not isinstance(info, dict) or not _REQUIRED_STEP_INFO <= set(info):
            _failure("Native frame and audio information is missing from a transition")
        if (info["runtime_kind"] != "installed_libretro_emulator"
            or info["source"] != "actual_isolated_native_core"):
            _failure("Reference or fabricated-mode records cannot be scored as native replay")
        for name in ("frame_sha256", "audio_sha256", "controls_sha256",
                     "previous_transition_digest"):
            _identity(info[name], _DIGEST, name)
        for name in ("native_runs", "video_callbacks", "audio_frames"):
            if type(info[name]) is not int or not 0 <= info[name] <= 2**63 - 1:
                _failure("Native callback counters must be bounded nonnegative integers")
    return trace


def compare_emulator_replays(traces: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Compare 2–10 independent *capture receipts* for the same exact rollout.

    Distinct random capture receipts discourage accidental duplicate submissions,
    but are not hardware attestation; untrusted parties could still fabricate
    trace data. This gate reports replay divergence, not learning quality.
    """
    if not isinstance(traces, (list, tuple)) or not 2 <= len(traces) <= MAX_REPEATS:
        _failure("A replay mirror audit requires 2 through 10 bounded native traces")
    records = [_validated_native_trace(item) for item in traces]
    reference = records[0]
    baseline = reference["source_lineage"]
    context_keys = (
        "runtime_kind", "core_id", "core_sha256", "content_digest",
        "registry_digest", "firmware_digest", "options_digest",
        "source_code_digest", "frames_per_step", "rights_evidence_digest",
    )
    if any(key not in baseline for key in context_keys):
        _failure("Native replay source context lacks complete immutable identity")
    seen = set()
    reference_actions = tuple(row["action"] for row in reference["transitions"])
    reference_controls = tuple(row["info"]["controls_sha256"] for row in reference["transitions"])
    for record in records:
        source = record["source_lineage"]
        if (record["environment"] != reference["environment"]
            or record["seed"] != reference["seed"]
            or record["steps"] != reference["steps"]
            or any(source.get(key) != baseline.get(key) for key in context_keys)
            or tuple(row["action"] for row in record["transitions"]) != reference_actions
            or tuple(row["info"]["controls_sha256"] for row in record["transitions"]) != reference_controls):
            _failure("Mirror runs must share exact core, ROM, firmware, actions and policy cadence")
        receipt = source["capture_nonce"]
        if receipt in seen or record["trace_digest"] in seen:
            _failure("Duplicated capture receipt or byte-identical trace is not another replay")
        seen.add(receipt)
        seen.add(record["trace_digest"])

    deltas = {name: 0 for name in _DIMENSIONS}
    first_divergence = None
    per_run = []
    for run_number, record in enumerate(records[1:], 2):
        mismatch_steps = []
        mismatched_categories = set()
        for index, (left, right) in enumerate(zip(reference["transitions"], record["transitions"], strict=True), 1):
            a, b = left["info"], right["info"]
            differences = {
                "video": a["frame_sha256"] != b["frame_sha256"],
                "audio": a["audio_sha256"] != b["audio_sha256"],
                "observation": left["next_observation"] != right["next_observation"],
                "reward": left["reward_components"] != right["reward_components"]
                    or left["reward"] != right["reward"],
                "transition_chain": left["transition_digest"] != right["transition_digest"],
                "native_callbacks": any(a[key] != b[key] for key in
                    ("native_runs", "video_callbacks", "audio_frames")),
            }
            if any(differences.values()):
                mismatch_steps.append(index)
                if first_divergence is None or index < first_divergence:
                    first_divergence = index
            for category, different in differences.items():
                if different:
                    deltas[category] += 1
                    mismatched_categories.add(category)
        per_run.append({
            "run": run_number,
            "trace_digest": record["trace_digest"],
            "divergent_step_count": len(mismatch_steps),
            "first_divergent_step": mismatch_steps[0] if mismatch_steps else None,
            "divergent_dimensions": sorted(mismatched_categories),
        })
    result = {
        "schema_version": SCHEMA,
        "status": "replay_divergence_detected" if first_divergence is not None else "self_reported_replay_consistent",
        "environment_digest": reference["environment"]["environment_digest"],
        "core_id": baseline["core_id"],
        "core_sha256": baseline["core_sha256"],
        "content_digest": baseline["content_digest"],
        "seed": reference["seed"],
        "steps_per_run": reference["steps"],
        "repeat_count": len(records),
        "first_divergent_step": first_divergence,
        "dimension_mismatch_counts": deltas,
        "run_comparisons": per_run,
        "capture_receipts_distinct": True,
        "independent_native_execution_attested": False,
        "gameplay_success_verified": False,
        "legal_rights_verified": False,
        "model_training_promotion_authorized": False,
        "evidence_limit": "Hashes and captured counters detect differences; replay matching does not prove correct hardware emulation or physical independence.",
    }
    result["audit_digest"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return result
