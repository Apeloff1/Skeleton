#!/usr/bin/env python3
"""Build a non-authoritative closure plan for P1 hardening/production gaps.

The planner joins the maturity frontier to canonical EVID-04 gap obligations.
It never writes risk bindings, accepted-risk records, accountability signoffs,
masterplan gaps, or maturity state. Closure remains governed by
machine/p1_risk_evidence_bindings.json and its existing fail-closed contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_p1_volume_accountability_candidates import (  # noqa: E402
    build_candidates as build_accountability_candidates,
)
from reconcile_p1_risk_evidence import (  # noqa: E402
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
)


BACKLOG = Path("machine/ai_p1_task_backlog.json")


class GapClosurePlanError(RuntimeError):
    """Gap closure planning input is malformed or inconsistent."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GapClosurePlanError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise GapClosurePlanError(f"{path} must contain an object")
    return payload


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _materialized(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe(
        str(value)
        for value in values
        if isinstance(value, str)
        and value.strip()
        and not value.startswith("planned:")
    )


def _tasks_by_volume(backlog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise GapClosurePlanError("P1 task backlog tasks must be a list")
    result: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise GapClosurePlanError("P1 task entries must be objects")
        task_id = task.get("task_id")
        refs = task.get("volume_refs")
        if not isinstance(task_id, str) or not task_id:
            raise GapClosurePlanError("P1 task_id is required")
        if not isinstance(refs, list):
            raise GapClosurePlanError(
                f"{task_id}: volume_refs must be a list"
            )
        for raw_ref in refs:
            result.setdefault(str(raw_ref), []).append(task)
    return result


def _owner_map(p1_map: dict[str, Any]) -> dict[str, dict[str, str]]:
    lanes = p1_map.get("lanes")
    if not isinstance(lanes, list):
        raise GapClosurePlanError("P1 execution map lanes must be a list")
    owner: dict[str, dict[str, str]] = {}
    for lane in lanes:
        if not isinstance(lane, dict):
            raise GapClosurePlanError("P1 lane entries must be objects")
        lane_id = lane.get("id")
        target = lane.get("target_maturity")
        refs = lane.get("primary_volume_refs")
        if not isinstance(lane_id, str) or not lane_id:
            raise GapClosurePlanError("P1 lane id is required")
        if target not in {"verified", "hardened", "production"}:
            raise GapClosurePlanError(
                f"{lane_id}: unsupported target maturity {target!r}"
            )
        if not isinstance(refs, list):
            raise GapClosurePlanError(
                f"{lane_id}: primary_volume_refs must be a list"
            )
        for raw_ref in refs:
            key = str(raw_ref)
            if key in owner:
                raise GapClosurePlanError(
                    f"duplicate primary-volume owner: {key}"
                )
            owner[key] = {
                "lane_id": lane_id,
                "target_floor": str(target),
            }
    return owner


def build_gap_closure_plan(root: Path = ROOT) -> dict[str, Any]:
    paths = {
        "master_plan": root / MASTER,
        "p1_execution_map": root / P1_MAP,
        "p1_task_backlog": root / BACKLOG,
        "adversarial_closure": root / ADVERSARIAL,
        "risk_policy": root / POLICY,
        "risk_registry": root / REGISTRY,
        "accountability_candidates": (
            root / "scripts/build_p1_volume_accountability_candidates.py"
        ),
        "risk_reconciler": root / "scripts/reconcile_p1_risk_evidence.py",
    }
    before = {name: _digest(path) for name, path in paths.items()}

    master = _load(paths["master_plan"])
    p1_map = _load(paths["p1_execution_map"])
    backlog = _load(paths["p1_task_backlog"])
    adversarial = _load(paths["adversarial_closure"])
    policy = _load(paths["risk_policy"])
    registry = _load(paths["risk_registry"])

    candidates = build_accountability_candidates(root)
    gap_candidates = {
        row["volume_key"]: row
        for row in candidates["records"]
        if "gap_closure_or_governed_disposition"
        in row["required_review_actions"]
    }
    if len(gap_candidates) != 84:
        raise GapClosurePlanError(
            "expected 84 target-floor gap-blocked volumes, got "
            f"{len(gap_candidates)}"
        )

    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise GapClosurePlanError("masterplan volumes must be a list")
    volume_by_key = {
        str(volume.get("key")): volume
        for volume in volumes
        if isinstance(volume, dict) and volume.get("key")
    }
    tasks_by_volume = _tasks_by_volume(backlog)
    owner = _owner_map(p1_map)

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    gap_obligations = [
        obligation
        for obligation in obligations
        if obligation.kind is RiskKind.GAP
        and obligation.source_ref.split(":", 1)[0] in gap_candidates
    ]
    if len(gap_obligations) != 168:
        raise GapClosurePlanError(
            "expected 168 target-floor gap obligations, got "
            f"{len(gap_obligations)}"
        )

    registry_rows = registry.get("records")
    if not isinstance(registry_rows, list):
        raise GapClosurePlanError("risk registry records must be a list")
    binding_ids = {
        str(row.get("obligation_id"))
        for row in registry_rows
        if isinstance(row, dict) and row.get("obligation_id")
    }

    obligations_by_volume: dict[str, list[Any]] = {}
    for obligation in gap_obligations:
        key = obligation.source_ref.split(":", 1)[0]
        obligations_by_volume.setdefault(key, []).append(obligation)

    packets: list[dict[str, Any]] = []
    for key in sorted(gap_candidates):
        volume = volume_by_key.get(key)
        if volume is None:
            raise GapClosurePlanError(f"missing masterplan volume: {key}")
        tasks = tasks_by_volume.get(key, [])
        if not tasks:
            raise GapClosurePlanError(f"{key}: no mapped P1 task")
        gap_statements = [
            str(item)
            for item in volume.get("gaps", [])
            if isinstance(item, str) and item.strip()
        ]
        if not gap_statements:
            raise GapClosurePlanError(f"{key}: no canonical gaps")

        volume_obligations = obligations_by_volume.get(key, [])
        if len(volume_obligations) != len(gap_statements):
            raise GapClosurePlanError(
                f"{key}: gap/obligation count mismatch "
                f"{len(gap_statements)} != {len(volume_obligations)}"
            )
        by_statement = {
            obligation.statement: obligation
            for obligation in volume_obligations
        }
        if set(by_statement) != set(gap_statements):
            raise GapClosurePlanError(
                f"{key}: canonical gap statements do not match EVID-04"
            )

        task_evidence = _dedupe(
            reference
            for task in tasks
            for reference in _materialized(task.get("evidence_refs"))
        )
        available_sources = _dedupe(
            _materialized(volume.get("implementation_paths"))
            + _materialized(volume.get("tests"))
            + _materialized(volume.get("evaluations"))
            + _materialized(volume.get("evidence"))
            + task_evidence
        )
        if not available_sources:
            raise GapClosurePlanError(
                f"{key}: no materialized evidence sources available"
            )

        closure_rows: list[dict[str, Any]] = []
        for statement in gap_statements:
            obligation = by_statement[statement]
            bound = obligation.obligation_id in binding_ids
            closure = {
                "obligation_id": obligation.obligation_id,
                "obligation_digest": obligation.obligation_digest,
                "source_ref": obligation.source_ref,
                "statement": statement,
                "default_severity": obligation.default_severity.value,
                "blocking_by_default": obligation.blocking_by_default,
                "binding_present": bound,
                "available_evidence_sources": available_sources,
                "resolution_paths": [
                    {
                        "kind": "evidence_binding_review",
                        "allowed": True,
                        "requires_materialized_evidence_refs": True,
                        "requires_owner": True,
                        "requires_classified_severity": True,
                        "requires_review_at": True,
                        "creates_binding": False,
                    },
                    {
                        "kind": "human_signed_accepted_risk_review",
                        "allowed": True,
                        "allowed_severities": ["high", "critical"],
                        "human_signer_required": True,
                        "identity_bound_signature_required": True,
                        "review_at_required": True,
                        "expiry_required": True,
                        "creates_acceptance": False,
                    },
                ],
            }
            closure["packet_digest"] = _canonical_digest(closure)
            closure_rows.append(closure)

        packet = {
            "volume_key": key,
            "lane_id": owner[key]["lane_id"],
            "target_floor": owner[key]["target_floor"],
            "accountability_id": gap_candidates[key]["accountability_id"],
            "mapped_task_ids": [
                str(task["task_id"])
                for task in tasks
            ],
            "gap_count": len(gap_statements),
            "bound_gap_count": sum(
                1 for row in closure_rows if row["binding_present"]
            ),
            "unbound_gap_count": sum(
                1 for row in closure_rows if not row["binding_present"]
            ),
            "obligations": closure_rows,
            "non_authoritative": True,
            "mutates_gap_state": False,
            "mutates_risk_registry": False,
            "creates_bindings": False,
            "creates_accepted_risk": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packets.append(packet)

    lane_counts: dict[str, int] = {}
    target_counts: dict[str, dict[str, int]] = {}
    for packet in packets:
        lane = packet["lane_id"]
        lane_counts[lane] = lane_counts.get(lane, 0) + packet["gap_count"]
        target = packet["target_floor"]
        entry = target_counts.setdefault(
            target,
            {"volume_count": 0, "gap_obligation_count": 0},
        )
        entry["volume_count"] += 1
        entry["gap_obligation_count"] += packet["gap_count"]

    total_bound = sum(packet["bound_gap_count"] for packet in packets)
    total_unbound = sum(packet["unbound_gap_count"] for packet in packets)

    after = {name: _digest(path) for name, path in paths.items()}
    if before != after:
        raise GapClosurePlanError(
            "canonical source files changed during closure planning"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-gap-closure-plan-v1",
        "non_authoritative": True,
        "mutates_gap_state": False,
        "mutates_risk_registry": False,
        "creates_bindings": False,
        "creates_accepted_risk": False,
        "human_signature_required_for_accepted_risk": True,
        "source_digests": before,
        "gap_blocked_volume_count": len(packets),
        "gap_obligation_count": len(gap_obligations),
        "bound_gap_obligation_count": total_bound,
        "unbound_gap_obligation_count": total_unbound,
        "target_counts": dict(sorted(target_counts.items())),
        "lane_gap_obligation_counts": dict(sorted(lane_counts.items())),
        "packets": packets,
    }
    report["report_digest"] = _canonical_digest(report)
    return report


def _canonical_text(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional path for the non-authoritative closure plan.",
    )
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_gap_closure_plan(ROOT)
    except GapClosurePlanError as exc:
        print(f"P1 gap closure plan: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_canonical_text(report), encoding="utf-8")

    if args.print_summary:
        summary = {
            key: report[key]
            for key in (
                "gap_blocked_volume_count",
                "gap_obligation_count",
                "bound_gap_obligation_count",
                "unbound_gap_obligation_count",
                "target_counts",
                "lane_gap_obligation_counts",
                "report_digest",
            )
        }
        print(json.dumps(summary, indent=2, sort_keys=True))

    print(
        "P1 gap closure plan: OK "
        f"({report['gap_blocked_volume_count']} volumes; "
        f"{report['gap_obligation_count']} gap obligations; "
        f"{report['bound_gap_obligation_count']} bound; "
        f"{report['unbound_gap_obligation_count']} unbound)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
