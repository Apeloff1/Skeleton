#!/usr/bin/env python3
"""Fail-closed validation for profile-gated native/JVM acceleration."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("machine/acceleration_policy.json")
REFS = ("VOL-032", "VOL-033")


class AccelerationControlError(RuntimeError):
    pass


def _load(root: Path, relative: str | Path) -> dict[str, Any]:
    path = root / Path(relative)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AccelerationControlError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise AccelerationControlError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AccelerationControlError(f"{relative} must contain an object")
    return payload


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise AccelerationControlError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise AccelerationControlError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise AccelerationControlError(f"non-canonical repository path: {value!r}")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    policy = _load(root, POLICY)
    master = _load(root, "machine/ai_master_plan.json")

    if policy.get("status") not in {"active", "active_stacked"}:
        raise AccelerationControlError("acceleration policy must be active")
    if policy.get("task_ref") != "P2-NATIVE-01":
        raise AccelerationControlError("acceleration task_ref drift")
    if policy.get("parent_lane") != "P2-QUAL-01":
        raise AccelerationControlError("acceleration parent lane drift")

    master_by_ref = {
        item["key"]: item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    bindings = policy.get("masterplan_bindings")
    if not isinstance(bindings, list):
        raise AccelerationControlError("masterplan_bindings must be a list")
    by_ref = {
        item.get("volume_ref"): item
        for item in bindings
        if isinstance(item, dict)
    }
    if set(by_ref) != set(REFS) or len(by_ref) != len(bindings):
        raise AccelerationControlError("acceleration masterplan binding coverage drift")
    for ref in REFS:
        volume = master_by_ref.get(ref)
        binding = by_ref[ref]
        if not isinstance(volume, dict):
            raise AccelerationControlError(f"masterplan missing {ref}")
        for field, expected in (
            ("title", volume.get("title")),
            ("accountability_id", volume.get("accountability_id")),
            ("required_gap_texts", volume.get("gaps", [])),
        ):
            if binding.get(field) != expected:
                raise AccelerationControlError(f"{ref}.{field} drift")

    runtime = policy.get("runtime_authority")
    if not isinstance(runtime, dict):
        raise AccelerationControlError("runtime_authority must be an object")
    required_runtime = {
        "selection_engine",
        "profiling_engine",
        "isolation_engine",
        "protocol_engine",
        "native_registry",
        "jvm_registry",
    }
    if set(runtime) != required_runtime:
        raise AccelerationControlError("runtime authority coverage drift")
    for label, relative in runtime.items():
        path = _repo_path(relative)
        if not (root / path).is_file():
            raise AccelerationControlError(f"{label} missing: {path}")

    selection = policy.get("selection_policy")
    if not isinstance(selection, dict):
        raise AccelerationControlError("selection_policy must be an object")
    if selection.get("default_route") != "reference":
        raise AccelerationControlError("reference path must remain the default route")
    if selection.get("evidence_required") is not True:
        raise AccelerationControlError("profile evidence must remain required")
    if selection.get("source_identity_required") is not True:
        raise AccelerationControlError("source identity must remain required")
    minimum_profile_runs = selection.get("minimum_profile_runs")
    minimum_environments = selection.get("minimum_distinct_environment_ids")
    minimum_speedup = selection.get("minimum_speedup")
    maximum_abs_error = selection.get("maximum_abs_error")
    maximum_crashes = selection.get("maximum_crashes")
    maximum_timeouts = selection.get("maximum_timeouts")
    if (
        not isinstance(minimum_profile_runs, int)
        or isinstance(minimum_profile_runs, bool)
        or minimum_profile_runs < 2
    ):
        raise AccelerationControlError("at least two profile runs are required")
    if (
        not isinstance(minimum_environments, int)
        or isinstance(minimum_environments, bool)
        or minimum_environments < 1
    ):
        raise AccelerationControlError("environment coverage must require at least one environment")
    if (
        isinstance(minimum_speedup, bool)
        or not isinstance(minimum_speedup, (int, float))
        or float(minimum_speedup) <= 1.0
    ):
        raise AccelerationControlError("speedup threshold must be > 1")
    if (
        isinstance(maximum_abs_error, bool)
        or not isinstance(maximum_abs_error, (int, float))
        or float(maximum_abs_error) < 0.0
    ):
        raise AccelerationControlError("maximum_abs_error must be non-negative numeric")
    if maximum_crashes != 0 or isinstance(maximum_crashes, bool):
        raise AccelerationControlError("automatic acceleration cannot tolerate crashes")
    if maximum_timeouts != 0 or isinstance(maximum_timeouts, bool):
        raise AccelerationControlError("automatic acceleration cannot tolerate timeouts")
    non_compensable = selection.get("non_compensable")
    expected_non_compensable = {
        "correctness",
        "error tolerance",
        "source identity",
        "sample count",
        "speedup",
        "crash budget",
        "timeout budget",
        "fallback availability",
        "isolation requirement",
        "protocol compatibility",
    }
    if not isinstance(non_compensable, list) or set(non_compensable) != expected_non_compensable:
        raise AccelerationControlError("non-compensable selection gates drift")

    isolation = policy.get("isolation_policy")
    if not isinstance(isolation, dict):
        raise AccelerationControlError("isolation_policy must be an object")
    for field in (
        "timeout_required",
        "bounded_output_required",
        "environment_allowlist_required",
        "fallback_on_isolation_failure",
    ):
        if isolation.get(field) is not True:
            raise AccelerationControlError(f"isolation policy must require {field}")

    protocol = policy.get("protocol_policy")
    if not isinstance(protocol, dict):
        raise AccelerationControlError("protocol_policy must be an object")
    if protocol.get("protocol_id") != "skeleton.acceleration.rpc":
        raise AccelerationControlError("acceleration protocol id drift")
    if protocol.get("supported_versions") != ["1.0"]:
        raise AccelerationControlError("acceleration protocol versions drift")
    if protocol.get("unknown_version") != "reject":
        raise AccelerationControlError("unknown accelerator protocol versions must reject")
    for field in (
        "request_id_required",
        "operation_required",
        "deadline_required",
        "fallback_on_negotiation_failure",
    ):
        if protocol.get(field) is not True:
            raise AccelerationControlError(f"protocol must require {field}")

    candidates = policy.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise AccelerationControlError("candidates must be non-empty")
    ids: set[str] = set()
    planes: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise AccelerationControlError("candidate must be an object")
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in ids:
            raise AccelerationControlError(f"invalid/duplicate candidate id: {candidate_id!r}")
        ids.add(candidate_id)
        plane = candidate.get("plane")
        if plane not in {"native", "jvm"}:
            raise AccelerationControlError(f"{candidate_id} has unsupported plane")
        planes.add(plane)

        for field in ("implementation", "registry"):
            path = _repo_path(candidate.get(field))
            if not (root / path).is_file():
                raise AccelerationControlError(f"{candidate_id} {field} missing: {path}")
        refs = candidate.get("reference_paths")
        if not isinstance(refs, list) or not refs:
            raise AccelerationControlError(f"{candidate_id} requires reference paths")
        for raw in refs:
            path = _repo_path(raw)
            if not (root / path).exists():
                raise AccelerationControlError(f"{candidate_id} fallback/reference missing: {path}")

        crash_risk = candidate.get("crash_risk")
        if crash_risk not in {"low", "medium", "high"}:
            raise AccelerationControlError(f"{candidate_id} crash risk invalid")
        if crash_risk in {"medium", "high"} and candidate.get("isolation") != "subprocess":
            raise AccelerationControlError(f"{candidate_id} must use subprocess isolation")
        if plane == "jvm" and candidate.get("protocol") != "skeleton.acceleration.rpc@1.0":
            raise AccelerationControlError(f"{candidate_id} JVM protocol negotiation drift")

        evidence = candidate.get("profile_evidence")
        if not isinstance(evidence, list):
            raise AccelerationControlError(f"{candidate_id} profile_evidence must be a list")
        if not evidence:
            if candidate.get("automatic_selection") is not False:
                raise AccelerationControlError(
                    f"{candidate_id} cannot auto-select without evidence"
                )
            if candidate.get("state") != "candidate_unpromoted":
                raise AccelerationControlError(
                    f"{candidate_id} evidence-free state must remain unpromoted"
                )

    if planes != {"native", "jvm"}:
        raise AccelerationControlError("policy must cover native and JVM candidates")

    jvm_protocol_clients = {
        "skeleton/observability/jvm_accelerator.py": (
            "CURRENT_PROTOCOL_VERSION",
            "negotiate_wire_major",
            "_validate_protocol_version(version)",
        ),
        "skeleton/memory/jvm_vector_accelerator.py": (
            "CURRENT_PROTOCOL_VERSION",
            "negotiate_wire_major",
            "_validate_protocol_version(version)",
        ),
        "skeleton/simulation/physics/jvm_broadphase_accelerator.py": (
            "CURRENT_PROTOCOL_VERSION",
            "negotiate_wire_major",
            "_validate_protocol_version(version)",
        ),
    }
    for relative, required_symbols in jvm_protocol_clients.items():
        text = (root / relative).read_text(encoding="utf-8")
        for symbol in required_symbols:
            if symbol not in text:
                raise AccelerationControlError(
                    f"{relative} missing shared JVM protocol binding: {symbol}"
                )

    java_peers = (
        "java-accelerators/observability/AcceleratorMain.java",
        "java-accelerators/vector/VectorSearchMain.java",
        "java-accelerators/physics/BroadPhaseMain.java",
    )
    for relative in java_peers:
        text = (root / relative).read_text(encoding="utf-8")
        if "static final short VERSION = 1;" not in text:
            raise AccelerationControlError(
                f"{relative} wire protocol version drift"
            )

    # AI-tree mirrors for new native controls must remain byte-identical.
    for name in ("selection.py", "profiling.py", "isolation.py", "protocol.py"):
        canonical = root / "skeleton/native" / name
        mirror = root / "skeleton/ai/runtime/native" / name
        if not mirror.is_file() or canonical.read_bytes() != mirror.read_bytes():
            raise AccelerationControlError(f"native AI-tree mirror drift: {name}")

    return {
        "status":"valid",
        "masterplan_binding_count":len(REFS),
        "candidate_count":len(candidates),
        "native_candidate_count":sum(item["plane"] == "native" for item in candidates),
        "jvm_candidate_count":sum(item["plane"] == "jvm" for item in candidates),
        "promoted_candidate_count":sum(bool(item.get("automatic_selection")) for item in candidates),
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo-root",default=".")
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    try:
        result=validate(Path(args.repo_root))
    except AccelerationControlError as exc:
        print(f"P2 acceleration control: FAIL: {exc}",file=sys.stderr)
        return 1
    print(json.dumps(result,sort_keys=True) if args.json else result)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
