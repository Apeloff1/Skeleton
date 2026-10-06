#!/usr/bin/env python3
"""Validate the enterprise AI superiority contract against the master plan.

This validator intentionally treats enterprise/superiority as evidence-bearing
states, not adjectives. It checks structure, complete critical-volume binding,
non-compensable gates, comparator definitions, dominance targets, and prevents
grade promotion without explicit evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("machine/enterprise_ai_superiority.json")
MASTER_PLAN = Path("machine/ai_master_plan.json")

REQUIRED_GRADE_STATES = (
    "designed",
    "implemented",
    "hardened",
    "enterprise_qualified",
    "superior",
)
REQUIRED_SCORECARDS = {
    "functional correctness and task quality",
    "security and abuse resistance",
    "privacy, governance and tenant isolation",
    "latency and tail latency",
    "throughput and saturation",
    "cost and resource efficiency",
    "reliability and safe degradation",
    "recovery, replay and rollback",
    "observability and auditability",
    "compatibility and migration",
    "operator control and supportability",
}
REQUIRED_FAULT_CLASSES = {
    "dependency unavailable",
    "dependency slow or partial",
    "process crash before and after durable commit",
    "duplicate/replayed request",
    "cancellation during expensive work",
    "saturation/backpressure",
    "stale worker or stale evidence",
    "malformed/oversized/untrusted input",
    "credential/policy/tenant mismatch",
    "rollback or reference-fallback activation",
}
REQUIRED_EVIDENCE_BINDINGS = {
    "git head",
    "baseline git/artifact identity",
    "policy/contract versions",
    "dataset/workload version",
    "model/provider and inference settings when applicable",
    "hardware/runtime/environment identity",
    "scorer/evaluator identity",
    "cost and resource budget",
    "raw results digest",
    "verdict and verifier identity",
}
REQUIRED_NON_COMPENSABLE_FRAGMENTS = (
    "critical security regressions",
    "cross-tenant or cross-user unauthorized disclosure",
    "unauthorized privileged side effects",
    "acknowledged authoritative state loss",
    "unbounded retry/recursion/delegation/background-work paths",
    "secret material emitted",
    "policy/privacy/residency weakening during fallback",
    "release without rollback/reference fallback",
    "enterprise claim without exact-head evidence",
)


class EnterpriseSuperiorityError(RuntimeError):
    """Machine authority violates enterprise AI superiority invariants."""


def _reject_constant(token: str) -> None:
    raise EnterpriseSuperiorityError(f"non-finite JSON token rejected: {token}")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise EnterpriseSuperiorityError(f"duplicate JSON object key: {key}")
        output[key] = value
    return output


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise EnterpriseSuperiorityError(f"cannot load {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EnterpriseSuperiorityError(f"{path} must contain a JSON object")
    return payload


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EnterpriseSuperiorityError(f"{label} must be canonical non-empty text")
    return value


def _text_list(value: Any, label: str, *, minimum: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise EnterpriseSuperiorityError(
            f"{label} must contain at least {minimum} entries"
        )
    rows = [_text(item, f"{label}[]") for item in value]
    if len(rows) != len(set(rows)):
        raise EnterpriseSuperiorityError(f"{label} must be unique")
    return rows


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EnterpriseSuperiorityError(f"{label} must be an object")
    return value


def _volume_map(master: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = master.get("volumes")
    if not isinstance(raw, list) or len(raw) != 421:
        raise EnterpriseSuperiorityError("master plan must contain VOL-000..VOL-420")
    output: dict[str, Mapping[str, Any]] = {}
    ids: set[int] = set()
    for item in raw:
        row = _mapping(item, "master volume")
        key = _text(row.get("key"), "master volume key")
        volume_id = row.get("id")
        if isinstance(volume_id, bool) or not isinstance(volume_id, int):
            raise EnterpriseSuperiorityError(f"{key} id must be integer")
        if key != f"VOL-{volume_id:03d}":
            raise EnterpriseSuperiorityError(f"{key} id/key mismatch")
        if key in output or volume_id in ids:
            raise EnterpriseSuperiorityError(f"duplicate master volume {key}")
        output[key] = row
        ids.add(volume_id)
    if ids != set(range(421)):
        raise EnterpriseSuperiorityError("master plan volume IDs must be contiguous 0..420")
    return output


def _validate_common(policy: Mapping[str, Any]) -> None:
    if policy.get("schema_version") != "skeleton.enterprise_ai_superiority.v1":
        raise EnterpriseSuperiorityError("unsupported superiority schema")
    if policy.get("status") not in {"active_design_authority", "active"}:
        raise EnterpriseSuperiorityError("superiority policy must be active")

    laws = _text_list(policy.get("laws"), "laws", minimum=8)
    law_blob = "\n".join(laws).lower()
    for token in (
        "implemented is not enterprise-qualified",
        "security, privacy, authority, tenant-isolation",
        "tail behavior",
        "exact-head",
        "expires",
    ):
        if token not in law_blob:
            raise EnterpriseSuperiorityError(f"missing enterprise law fragment: {token}")

    grade = _mapping(policy.get("grade_model"), "grade_model")
    states = _text_list(grade.get("states"), "grade_model.states", minimum=5)
    if tuple(states) != REQUIRED_GRADE_STATES:
        raise EnterpriseSuperiorityError("grade model state order drift")
    meanings = _mapping(grade.get("meanings"), "grade_model.meanings")
    if set(meanings) != set(REQUIRED_GRADE_STATES):
        raise EnterpriseSuperiorityError("every grade state requires a meaning")

    dominance = _mapping(policy.get("dominance_rule"), "dominance_rule")
    minimum_wins = dominance.get("minimum_dominance_target_wins")
    if isinstance(minimum_wins, bool) or not isinstance(minimum_wins, int) or minimum_wins < 3:
        raise EnterpriseSuperiorityError("dominance requires at least three target wins")
    if dominance.get("primary_outcome_must_win_or_meet_declared_strict_target") is not True:
        raise EnterpriseSuperiorityError("primary outcome must be non-optional")
    if "Pareto" not in _text(dominance.get("pareto_rule"), "dominance_rule.pareto_rule"):
        raise EnterpriseSuperiorityError("dominance must require Pareto improvement")

    common = _mapping(policy.get("common_contract"), "common_contract")
    scorecards = set(_text_list(common.get("required_scorecards"), "required_scorecards"))
    if not REQUIRED_SCORECARDS.issubset(scorecards):
        raise EnterpriseSuperiorityError("enterprise scorecard coverage incomplete")
    faults = set(_text_list(common.get("required_fault_campaigns"), "required_fault_campaigns"))
    if not REQUIRED_FAULT_CLASSES.issubset(faults):
        raise EnterpriseSuperiorityError("fault campaign coverage incomplete")
    evidence = set(_text_list(common.get("evidence_bundle_must_bind"), "evidence_bundle_must_bind"))
    if not REQUIRED_EVIDENCE_BINDINGS.issubset(evidence):
        raise EnterpriseSuperiorityError("evidence identity coverage incomplete")

    non_comp = _text_list(
        common.get("non_compensable_gates"),
        "non_compensable_gates",
        minimum=9,
    )
    blob = "\n".join(non_comp).lower()
    for fragment in REQUIRED_NON_COMPENSABLE_FRAGMENTS:
        if fragment.lower() not in blob:
            raise EnterpriseSuperiorityError(
                f"missing non-compensable gate fragment: {fragment}"
            )


def _validate_profiles(
    policy: Mapping[str, Any],
    master_volumes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    archetypes = _mapping(policy.get("archetypes"), "archetypes")
    if len(archetypes) < 20:
        raise EnterpriseSuperiorityError("enterprise archetype coverage is too thin")

    for name, raw in archetypes.items():
        _text(name, "archetype name")
        row = _mapping(raw, f"archetype {name}")
        _text(row.get("comparator"), f"archetype {name}.comparator")
        _text(row.get("primary_outcome"), f"archetype {name}.primary_outcome")
        targets = row.get("dominance_targets")
        if not isinstance(targets, list) or len(targets) < 3:
            raise EnterpriseSuperiorityError(
                f"archetype {name} requires at least three dominance targets"
            )
        for target in targets:
            item = _mapping(target, f"archetype {name} target")
            for field in ("metric", "target", "comparison"):
                _text(item.get(field), f"archetype {name} target.{field}")

    coverage = _mapping(policy.get("coverage"), "coverage")
    if coverage.get("all_masterplan_volumes_inherit_common_contract") is not True:
        raise EnterpriseSuperiorityError("all volumes must inherit common contract")
    dedicated = _text_list(
        coverage.get("dedicated_profiles_required_for"),
        "dedicated_profiles_required_for",
        minimum=1,
    )
    for ref in dedicated:
        if ref not in master_volumes:
            raise EnterpriseSuperiorityError(f"unknown dedicated profile volume: {ref}")

    raw_profiles = policy.get("profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise EnterpriseSuperiorityError("profiles must be non-empty")

    profiles: dict[str, Mapping[str, Any]] = {}
    profile_ids: set[str] = set()
    for raw in raw_profiles:
        row = _mapping(raw, "profile")
        profile_id = _text(row.get("id"), "profile.id")
        volume_ref = _text(row.get("volume_ref"), f"{profile_id}.volume_ref")
        if profile_id in profile_ids or volume_ref in profiles:
            raise EnterpriseSuperiorityError(f"duplicate profile binding: {profile_id}")
        if volume_ref not in master_volumes:
            raise EnterpriseSuperiorityError(f"{profile_id} references unknown volume")
        expected_id = f"ENT-{volume_ref}"
        if profile_id != expected_id:
            raise EnterpriseSuperiorityError(
                f"{volume_ref} profile id must be {expected_id}"
            )
        archetype = _text(row.get("archetype"), f"{profile_id}.archetype")
        if archetype not in archetypes:
            raise EnterpriseSuperiorityError(f"{profile_id} archetype is unknown")
        _text(row.get("title"), f"{profile_id}.title")
        _text(row.get("comparator"), f"{profile_id}.comparator")
        _text(row.get("primary_outcome"), f"{profile_id}.primary_outcome")

        targets = row.get("dominance_targets")
        if not isinstance(targets, list) or len(targets) < 3:
            raise EnterpriseSuperiorityError(
                f"{profile_id} requires at least three dominance targets"
            )
        metric_names: set[str] = set()
        for target in targets:
            item = _mapping(target, f"{profile_id}.dominance_target")
            metric = _text(item.get("metric"), f"{profile_id}.metric")
            _text(item.get("target"), f"{profile_id}.target")
            _text(item.get("comparison"), f"{profile_id}.comparison")
            if metric in metric_names:
                raise EnterpriseSuperiorityError(
                    f"{profile_id} duplicate dominance metric: {metric}"
                )
            metric_names.add(metric)

        _text_list(row.get("hard_gates"), f"{profile_id}.hard_gates", minimum=5)
        _text_list(
            row.get("evidence_required"),
            f"{profile_id}.evidence_required",
            minimum=7,
        )

        state = row.get("qualification_state")
        if state not in {"unqualified", "enterprise_qualified", "superior"}:
            raise EnterpriseSuperiorityError(
                f"{profile_id} invalid qualification_state: {state!r}"
            )
        if state != "unqualified":
            evidence = _text_list(
                row.get("qualification_evidence"),
                f"{profile_id}.qualification_evidence",
                minimum=3,
            )
            if not any("git" in item.lower() or "head" in item.lower() for item in evidence):
                raise EnterpriseSuperiorityError(
                    f"{profile_id} promoted without exact-head identity evidence"
                )

        profiles[volume_ref] = row
        profile_ids.add(profile_id)

    if set(dedicated) != set(profiles):
        missing = sorted(set(dedicated) - set(profiles))
        extra = sorted(set(profiles) - set(dedicated))
        raise EnterpriseSuperiorityError(
            f"dedicated/profile mismatch missing={missing} extra={extra}"
        )
    return profiles


def _validate_master_bindings(
    policy: Mapping[str, Any],
    master: Mapping[str, Any],
    master_volumes: Mapping[str, Mapping[str, Any]],
    profiles: Mapping[str, Mapping[str, Any]],
) -> None:
    authority = _mapping(master.get("authority"), "master.authority")
    if authority.get("enterprise_ai_superiority") != str(POLICY):
        raise EnterpriseSuperiorityError("master authority missing superiority policy")

    enterprise = _mapping(master.get("enterprise_grade_policy"), "enterprise_grade_policy")
    if enterprise.get("authority") != str(POLICY):
        raise EnterpriseSuperiorityError("master enterprise policy authority drift")
    if enterprise.get("target_grade") != "superior":
        raise EnterpriseSuperiorityError("master enterprise target must be superior")
    _text(enterprise.get("anti_shortcut"), "enterprise_grade_policy.anti_shortcut")
    _text(enterprise.get("required_for_product_claim"), "enterprise_grade_policy.required_for_product_claim")

    complete_claim = _mapping(
        _mapping(
            policy.get("coverage"),
            "coverage",
        ).get("complete_enterprise_ai_claim"),
        "coverage.complete_enterprise_ai_claim",
    )
    if complete_claim.get("all_421_volumes_minimum_grade") != "enterprise_qualified":
        raise EnterpriseSuperiorityError(
            "complete enterprise AI claim must require all volumes enterprise_qualified"
        )
    if complete_claim.get("dedicated_profile_minimum_grade") != "superior":
        raise EnterpriseSuperiorityError(
            "dedicated profile minimum grade must be superior"
        )

    for volume_ref, volume in master_volumes.items():
        state = volume.get("enterprise_grade_state")
        if state not in REQUIRED_GRADE_STATES:
            raise EnterpriseSuperiorityError(
                f"{volume_ref} invalid enterprise_grade_state: {state!r}"
            )
        target = volume.get("enterprise_grade_target")
        if volume_ref in profiles:
            if target != "superior":
                raise EnterpriseSuperiorityError(
                    f"{volume_ref} enterprise grade target must be superior"
                )
        elif target != "enterprise_qualified":
            raise EnterpriseSuperiorityError(
                f"{volume_ref} non-dedicated enterprise target must be enterprise_qualified"
            )

    for volume_ref, profile in profiles.items():
        volume = master_volumes[volume_ref]
        expected_profile = profile["id"]
        if volume.get("enterprise_superiority_profile") != expected_profile:
            raise EnterpriseSuperiorityError(
                f"{volume_ref} master binding does not reference {expected_profile}"
            )
        state = volume["enterprise_grade_state"]
        if state in {"enterprise_qualified", "superior"}:
            if profile.get("qualification_state") not in {
                "enterprise_qualified",
                "superior",
            }:
                raise EnterpriseSuperiorityError(
                    f"{volume_ref} master grade exceeds profile evidence state"
                )
        if state == "superior" and profile.get("qualification_state") != "superior":
            raise EnterpriseSuperiorityError(
                f"{volume_ref} superior grade requires superior profile state"
            )


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    policy = _load(root / POLICY)
    master = _load(root / MASTER_PLAN)
    _validate_common(policy)
    volumes = _volume_map(master)
    profiles = _validate_profiles(policy, volumes)
    _validate_master_bindings(policy, master, volumes, profiles)

    qualified = sum(
        1 for profile in profiles.values()
        if profile.get("qualification_state") == "enterprise_qualified"
    )
    superior = sum(
        1 for profile in profiles.values()
        if profile.get("qualification_state") == "superior"
    )
    return {
        "status": "valid",
        "schema_version": policy["schema_version"],
        "policy_version": policy["version"],
        "master_plan_version": master.get("plan_version"),
        "master_volume_count": len(volumes),
        "dedicated_profile_count": len(profiles),
        "archetype_count": len(policy["archetypes"]),
        "enterprise_qualified_profiles": qualified,
        "superior_profiles": superior,
        "all_volumes_inherit_common_contract": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.root))
    except EnterpriseSuperiorityError as exc:
        print(f"enterprise AI superiority: FAIL: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("enterprise AI superiority: PASS")
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
