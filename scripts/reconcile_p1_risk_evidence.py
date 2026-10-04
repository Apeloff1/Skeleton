#!/usr/bin/env python3
"""Reconcile P1 risk/gap obligations with governed evidence bindings.

The report is non-authoritative. It inventories canonical P1 obligations,
validates any supplied bindings, and reports unresolved blocking work without
mutating masterplan, evidence, accountability or binding state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.risk_evidence import (
    ACCEPTED_RISK_SIGNATURE_METHODS,
    ACCEPTED_RISK_SIGNER_TYPES,
    AcceptedRisk,
    RiskEvidenceBinding,
    RiskEvidenceError,
    RiskKind,
    RiskObligation,
    RiskSeverity,
    canonical_digest,
    evaluate_risk_binding,
    make_obligation_id,
)


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
P1_MAP = Path("machine/ai_p1_execution_map.json")
ADVERSARIAL = Path("machine/ai_adversarial_closure.json")
CLOSURE = Path("machine/ai_closure_evidence.json")
POLICY = Path("machine/p1_risk_evidence_policy.json")
REGISTRY = Path("machine/p1_risk_evidence_bindings.json")

class RiskReconciliationError(RuntimeError):
    """Repository risk reconciliation inputs are malformed."""


def retired_gap_owner_from_id(obligation_id: str) -> str | None:
    """Return the canonical owner for a historical volume-gap binding ID."""
    prefix = "P1-GAP-"
    if not isinstance(obligation_id, str) or not obligation_id.startswith(prefix):
        return None
    body = obligation_id[len(prefix):]
    source_ref, separator, suffix = body.rpartition("-")
    if not separator or len(suffix) != 16:
        return None
    volume_key, separator, source_suffix = source_ref.partition(":gap:")
    if (
        not separator
        or not volume_key.startswith("VOL-")
        or len(source_suffix) != 10
        or not all(ch in "0123456789abcdef" for ch in source_suffix + suffix)
    ):
        return None
    return "ACC-" + volume_key


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RiskReconciliationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise RiskReconciliationError(f"{path} must contain an object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise RiskReconciliationError(f"{field} must be ISO-8601 text")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RiskReconciliationError(f"{field} is invalid ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise RiskReconciliationError(f"{field} must be timezone-aware")
    return result


def _source_rule(policy: dict[str, Any], key: str) -> dict[str, Any]:
    sources = policy.get("sources")
    if not isinstance(sources, dict):
        raise RiskReconciliationError("risk policy sources must be an object")
    value = sources.get(key)
    if not isinstance(value, dict):
        raise RiskReconciliationError(f"risk policy missing source rule {key}")
    return value


def _obligation(
    *,
    kind: RiskKind,
    source_ref: str,
    statement: str,
    source_payload: object,
    rule: dict[str, Any],
    required_evidence_modes: tuple[str, ...] = (),
) -> RiskObligation:
    try:
        severity = RiskSeverity(rule.get("default_severity"))
    except ValueError as exc:
        raise RiskReconciliationError(
            f"invalid default severity for {source_ref}"
        ) from exc
    blocking = rule.get("blocking_by_default")
    if not isinstance(blocking, bool):
        raise RiskReconciliationError(
            f"blocking_by_default must be boolean for {source_ref}"
        )
    return RiskObligation(
        obligation_id=make_obligation_id(kind, source_ref, statement),
        kind=kind,
        source_ref=source_ref,
        statement=statement,
        source_digest=canonical_digest(source_payload),
        default_severity=severity,
        blocking_by_default=blocking,
        required_evidence_modes=required_evidence_modes,
    )


def derive_obligations(
    master: dict[str, Any],
    p1_map: dict[str, Any],
    adversarial: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[RiskObligation, ...]:
    volumes = master.get("volumes")
    lanes = p1_map.get("lanes")
    axes = adversarial.get("closure_axes")
    if not isinstance(volumes, list):
        raise RiskReconciliationError("master plan volumes must be a list")
    if not isinstance(lanes, list):
        raise RiskReconciliationError("P1 lanes must be a list")
    if not isinstance(axes, list):
        raise RiskReconciliationError("adversarial closure axes must be a list")

    primary_refs: set[str] = set()
    p1_packages: set[str] = set()
    for lane in lanes:
        if not isinstance(lane, dict):
            raise RiskReconciliationError("P1 lane entries must be objects")
        refs = lane.get("primary_volume_refs")
        packages = lane.get("work_package_refs")
        if not isinstance(refs, list) or not isinstance(packages, list):
            raise RiskReconciliationError("P1 lane scope is malformed")
        primary_refs.update(str(item) for item in refs)
        p1_packages.update(str(item) for item in packages)

    volume_by_key = {
        str(row.get("key")): row
        for row in volumes
        if isinstance(row, dict) and row.get("key")
    }
    missing = sorted(primary_refs - set(volume_by_key))
    if missing:
        raise RiskReconciliationError(
            "missing P1 primary volumes: " + ",".join(missing)
        )

    risk_rule = _source_rule(policy, "volume_risk")
    gap_rule = _source_rule(policy, "volume_gap")
    adv_rule = _source_rule(policy, "adversarial_axis")
    obligations: list[RiskObligation] = []

    for key in sorted(primary_refs):
        volume = volume_by_key[key]
        risks = volume.get("risks")
        gaps = volume.get("gaps")
        if not isinstance(risks, list) or not isinstance(gaps, list):
            raise RiskReconciliationError(f"{key}: risks/gaps must be lists")
        for statement in risks:
            if not isinstance(statement, str) or not statement.strip():
                raise RiskReconciliationError(f"{key}: invalid risk statement")
            suffix = canonical_digest(statement)[:10]
            source_ref = f"{key}:risk:{suffix}"
            obligations.append(
                _obligation(
                    kind=RiskKind.RISK,
                    source_ref=source_ref,
                    statement=statement,
                    source_payload={
                        "volume": key,
                        "kind": "risk",
                        "statement": statement,
                    },
                    rule=risk_rule,
                )
            )
        for statement in gaps:
            if not isinstance(statement, str) or not statement.strip():
                raise RiskReconciliationError(f"{key}: invalid gap statement")
            suffix = canonical_digest(statement)[:10]
            source_ref = f"{key}:gap:{suffix}"
            obligations.append(
                _obligation(
                    kind=RiskKind.GAP,
                    source_ref=source_ref,
                    statement=statement,
                    source_payload={
                        "volume": key,
                        "kind": "gap",
                        "statement": statement,
                    },
                    rule=gap_rule,
                )
            )

    for axis in axes:
        if not isinstance(axis, dict):
            raise RiskReconciliationError("adversarial axis must be an object")
        axis_id = axis.get("id")
        statement = axis.get("gap")
        applicable = axis.get("applicable_work_packages")
        modes = axis.get("required_evidence_modes")
        if (
            not isinstance(axis_id, str)
            or not isinstance(statement, str)
            or not isinstance(applicable, list)
            or not isinstance(modes, list)
        ):
            raise RiskReconciliationError("adversarial axis is malformed")
        if not (set(str(item) for item in applicable) & p1_packages):
            continue
        obligations.append(
            _obligation(
                kind=RiskKind.ADVERSARIAL,
                source_ref=axis_id,
                statement=statement,
                source_payload=axis,
                rule=adv_rule,
                required_evidence_modes=tuple(str(item) for item in modes),
            )
        )

    by_id: dict[str, RiskObligation] = {}
    for item in obligations:
        if item.obligation_id in by_id:
            raise RiskReconciliationError(
                f"duplicate obligation identity: {item.obligation_id}"
            )
        by_id[item.obligation_id] = item
    return tuple(by_id[key] for key in sorted(by_id))


def _accepted_risk(raw: object) -> AcceptedRisk | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RiskReconciliationError("accepted_risk must be an object")
    try:
        return AcceptedRisk(
            obligation_id=raw["obligation_id"],
            obligation_digest=raw["obligation_digest"],
            owner_id=raw["owner_id"],
            severity=raw["severity"],
            accepted_at=_time(raw["accepted_at"], "accepted_at"),
            review_at=_time(raw["review_at"], "review_at"),
            expires_at=_time(raw["expires_at"], "expires_at"),
            signer_id=raw["signer_id"],
            signer_type=raw["signer_type"],
            git_sha=raw["git_sha"],
            signature_method=raw["signature_method"],
            signature_ref=raw["signature_ref"],
            statement=raw["statement"],
        )
    except (KeyError, RiskEvidenceError) as exc:
        raise RiskReconciliationError(
            f"invalid accepted-risk record: {exc}"
        ) from exc


def _binding(raw: object) -> RiskEvidenceBinding:
    if not isinstance(raw, dict):
        raise RiskReconciliationError("binding record must be an object")
    evidence_raw = raw.get("evidence", [])
    if not isinstance(evidence_raw, list):
        raise RiskReconciliationError("binding evidence must be a list")
    evidence: list[EvidenceRef] = []
    for row in evidence_raw:
        if not isinstance(row, dict):
            raise RiskReconciliationError("evidence entries must be objects")
        allowed = {"source", "digest", "category"}
        unknown = set(row) - allowed
        if unknown:
            raise RiskReconciliationError(
                "evidence contains unknown fields: "
                + ",".join(sorted(unknown))
            )
        try:
            evidence.append(
                EvidenceRef(
                    source=row["source"],
                    digest=row["digest"],
                    category=row["category"],
                )
            )
        except KeyError as exc:
            raise RiskReconciliationError("incomplete evidence entry") from exc
    try:
        return RiskEvidenceBinding(
            obligation_id=raw["obligation_id"],
            obligation_digest=raw["obligation_digest"],
            owner_id=raw["owner_id"],
            severity=raw["severity"],
            disposition=raw["disposition"],
            bound_at=_time(raw["bound_at"], "bound_at"),
            review_at=_time(raw["review_at"], "review_at"),
            evidence=tuple(evidence),
            accepted_risk=_accepted_risk(raw.get("accepted_risk")),
        )
    except (KeyError, RiskEvidenceError) as exc:
        raise RiskReconciliationError(f"invalid binding record: {exc}") from exc


def _validate_policy_registry(
    policy: dict[str, Any],
    registry: dict[str, Any],
) -> None:
    if policy.get("schema_version") != 1:
        raise RiskReconciliationError("risk policy schema_version must equal 1")
    if policy.get("policy_id") != "skeleton.p1.risk_gap_evidence_binding":
        raise RiskReconciliationError("risk policy id drift")
    if policy.get("policy_version") != "1.0.0":
        raise RiskReconciliationError("risk policy version drift")
    if policy.get("task_id") != "P1-EVID-04":
        raise RiskReconciliationError("risk policy task_id drift")
    if policy.get("accountability_ref") != "ACC-P1-EVID-04":
        raise RiskReconciliationError("risk policy accountability drift")
    if policy.get("non_authoritative") is not True:
        raise RiskReconciliationError("risk policy must remain non-authoritative")

    binding_rules = policy.get("binding_rules")
    if not isinstance(binding_rules, dict):
        raise RiskReconciliationError("risk policy binding_rules must be an object")
    signer_types = binding_rules.get("accepted_risk_signer_types")
    if (
        not isinstance(signer_types, list)
        or len(signer_types) != len(set(signer_types))
        or set(signer_types) != set(ACCEPTED_RISK_SIGNER_TYPES)
    ):
        raise RiskReconciliationError(
            "accepted-risk signer type policy drift"
        )
    signature_methods = binding_rules.get(
        "accepted_risk_signature_methods"
    )
    if (
        not isinstance(signature_methods, list)
        or len(signature_methods) != len(set(signature_methods))
        or set(signature_methods) != set(ACCEPTED_RISK_SIGNATURE_METHODS)
    ):
        raise RiskReconciliationError(
            "accepted-risk signature method policy drift"
        )

    if registry.get("schema_version") != 1:
        raise RiskReconciliationError("risk registry schema_version must equal 1")
    if registry.get("registry_id") != "skeleton.p1.risk_gap_evidence_bindings":
        raise RiskReconciliationError("risk registry id drift")
    if registry.get("status") != "active":
        raise RiskReconciliationError("risk registry must be active")
    if registry.get("task_id") != "P1-EVID-04":
        raise RiskReconciliationError("risk registry task_id drift")
    if registry.get("accountability_ref") != "ACC-P1-EVID-04":
        raise RiskReconciliationError("risk registry accountability drift")
    if not isinstance(registry.get("records"), list):
        raise RiskReconciliationError("risk registry records must be a list")


def reconcile_repository(
    root: Path = ROOT,
    *,
    evaluated_at: datetime,
) -> dict[str, Any]:
    paths = {
        "master_plan": root / MASTER,
        "p1_execution_map": root / P1_MAP,
        "adversarial_closure": root / ADVERSARIAL,
        "closure_evidence": root / CLOSURE,
        "risk_policy": root / POLICY,
        "risk_registry": root / REGISTRY,
        "engine_contract": root / "skeleton/contracts/risk_evidence.py",
        "engine_runner": root / "scripts/reconcile_p1_risk_evidence.py",
    }
    before = {name: _digest(path) for name, path in paths.items()}
    master = _load(paths["master_plan"])
    p1_map = _load(paths["p1_execution_map"])
    adversarial = _load(paths["adversarial_closure"])
    closure = _load(paths["closure_evidence"])
    policy = _load(paths["risk_policy"])
    registry = _load(paths["risk_registry"])
    _validate_policy_registry(policy, registry)

    authority = master.get("authority")
    if not isinstance(authority, dict):
        raise RiskReconciliationError("master plan authority must be an object")
    expected_authority = {
        "p1_risk_evidence_policy": str(POLICY),
        "p1_risk_evidence_registry": str(REGISTRY),
        "p1_risk_evidence_engine": "scripts/reconcile_p1_risk_evidence.py",
        "p1_risk_evidence_contract": "skeleton/contracts/risk_evidence.py",
    }
    for key, expected in expected_authority.items():
        if authority.get(key) != expected:
            raise RiskReconciliationError(
                f"master plan {key} authority pointer drift"
            )

    closure_entries = closure.get("entries")
    if not isinstance(closure_entries, list) or not closure_entries:
        raise RiskReconciliationError(
            "baseline closure evidence entries must be non-empty"
        )

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    expectations = policy.get("inventory_expectations")
    if not isinstance(expectations, dict):
        raise RiskReconciliationError("inventory_expectations must be an object")
    primary_count = len(
        {
            ref
            for lane in p1_map.get("lanes", [])
            if isinstance(lane, dict)
            for ref in lane.get("primary_volume_refs", [])
        }
    )
    live_counts = {
        "p1_primary_volume_count": primary_count,
        "volume_risk_count": sum(
            1 for item in obligations if item.kind is RiskKind.RISK
        ),
        "volume_gap_count": sum(
            1 for item in obligations if item.kind is RiskKind.GAP
        ),
        "applicable_adversarial_axis_count": sum(
            1 for item in obligations if item.kind is RiskKind.ADVERSARIAL
        ),
        "total_obligation_count": len(obligations),
    }
    for key in (
        "p1_primary_volume_count",
        "volume_risk_count",
        "applicable_adversarial_axis_count",
    ):
        if expectations.get(key) != live_counts[key]:
            raise RiskReconciliationError(
                f"risk obligation inventory drift for {key}: "
                f"expected={expectations.get(key)!r} actual={live_counts[key]}"
            )
    expected_gap_count = expectations.get("volume_gap_count")
    expected_total_count = expectations.get("total_obligation_count")
    if not isinstance(expected_gap_count, int) or not isinstance(
        expected_total_count, int
    ):
        raise RiskReconciliationError("risk obligation inventory expectations are malformed")
    retired_expected_count = expected_gap_count - live_counts["volume_gap_count"]
    total_delta = expected_total_count - live_counts["total_obligation_count"]
    if retired_expected_count < 0 or total_delta != retired_expected_count:
        raise RiskReconciliationError(
            "historical retired-gap inventory does not reconcile with live obligations"
        )
    counts = dict(live_counts)
    counts["volume_gap_count"] += retired_expected_count
    counts["total_obligation_count"] += retired_expected_count
    for key, actual in counts.items():
        if expectations.get(key) != actual:
            raise RiskReconciliationError(
                f"risk obligation inventory drift for {key}: "
                f"expected={expectations.get(key)!r} actual={actual}"
            )

    bindings: dict[str, RiskEvidenceBinding] = {}
    for raw in registry["records"]:
        binding = _binding(raw)
        if binding.obligation_id in bindings:
            raise RiskReconciliationError(
                f"duplicate risk binding: {binding.obligation_id}"
            )
        bindings[binding.obligation_id] = binding

    obligation_by_id = {item.obligation_id: item for item in obligations}
    unknown = sorted(set(bindings) - set(obligation_by_id))
    retired_present: list[str] = []
    unexpected: list[str] = []
    for obligation_id in unknown:
        binding = bindings[obligation_id]
        expected_owner = retired_gap_owner_from_id(obligation_id)
        if (
            expected_owner is None
            or binding.owner_id != expected_owner
            or binding.disposition.value != "evidence"
            or not binding.evidence
            or binding.accepted_risk is not None
        ):
            unexpected.append(obligation_id)
            continue
        retired_present.append(obligation_id)
    if unexpected:
        raise RiskReconciliationError(
            "bindings reference unknown obligations: " + ",".join(unexpected)
        )
    if len(retired_present) > retired_expected_count:
        raise RiskReconciliationError(
            "retired gap bindings exceed governed historical inventory"
        )
    if (
        len(bindings) == counts["total_obligation_count"]
        and len(retired_present) != retired_expected_count
    ):
        raise RiskReconciliationError(
            "complete binding registry does not cover governed retired gap inventory"
        )

    rows: list[dict[str, Any]] = []
    for obligation in obligations:
        decision = evaluate_risk_binding(
            obligation,
            bindings.get(obligation.obligation_id),
            evaluated_at=evaluated_at,
        )
        rows.append(
            {
                "obligation": obligation.as_dict(),
                "obligation_digest": obligation.obligation_digest,
                "binding": (
                    bindings[obligation.obligation_id].as_dict()
                    if obligation.obligation_id in bindings
                    else None
                ),
                "evaluation": decision.as_dict(),
            }
        )

    after = {name: _digest(path) for name, path in paths.items()}
    if before != after:
        raise RiskReconciliationError(
            "canonical risk source files changed during reconciliation"
        )

    unresolved_blocking = [
        row
        for row in rows
        if row["evaluation"]["blocking"]
        and not row["evaluation"]["resolved"]
    ]
    unclassified = [
        row
        for row in rows
        if row["evaluation"]["severity"] == "unclassified"
    ]
    resolved = [
        row for row in rows if row["evaluation"]["resolved"]
    ]
    disposition_counts: dict[str, int] = {}
    for row in rows:
        disposition = row["evaluation"]["disposition"] or "unbound"
        disposition_counts[disposition] = (
            disposition_counts.get(disposition, 0) + 1
        )
    historical_disposition_counts = dict(disposition_counts)
    for obligation_id in retired_present:
        disposition = bindings[obligation_id].disposition or "unbound"
        historical_disposition_counts[disposition] = (
            historical_disposition_counts.get(disposition, 0) + 1
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-risk-gap-evidence-binding-v1",
        "evaluated_at": evaluated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_digests": before,
        "source_mutation_detected": False,
        "baseline_closure_entry_count": len(closure_entries),
        "inventory": counts,
        "live_inventory": live_counts,
        "binding_count": len(bindings),
        "live_binding_count": len(set(bindings) & set(obligation_by_id)),
        "historical_binding_count": len(bindings),
        "retired_binding_count": len(retired_present),
        "retired_expected_count": retired_expected_count,
        "resolved_count": len(resolved) + len(retired_present),
        "live_resolved_count": len(resolved),
        "historical_resolved_count": len(resolved) + len(retired_present),
        "unresolved_blocking_count": len(unresolved_blocking),
        "unclassified_count": len(unclassified),
        "disposition_counts": dict(sorted(historical_disposition_counts.items())),
        "live_disposition_counts": dict(sorted(disposition_counts.items())),
        "historical_disposition_counts": dict(sorted(historical_disposition_counts.items())),
        "retired_obligation_ids": retired_present,
        "records": rows,
        "non_authoritative": True,
    }
    report["report_digest"] = canonical_digest(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluated-at", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--require-resolved", action="store_true")
    args = parser.parse_args(argv)

    try:
        evaluated_at = _time(args.evaluated_at, "evaluated_at")
        report = reconcile_repository(ROOT, evaluated_at=evaluated_at)
    except (RiskReconciliationError, RiskEvidenceError) as exc:
        print(f"P1 risk evidence reconciliation: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if args.print_summary:
        summary = {
            key: report[key]
            for key in (
                "engine",
                "evaluated_at",
                "inventory",
                "binding_count",
                "resolved_count",
                "unresolved_blocking_count",
                "unclassified_count",
                "disposition_counts",
                "report_digest",
                "non_authoritative",
            )
        }
        print(json.dumps(summary, indent=2, sort_keys=True))

    if args.require_resolved and (
        report["unresolved_blocking_count"] != 0
        or report["unclassified_count"] != 0
    ):
        print(
            "P1 risk evidence reconciliation: unresolved blocking obligations",
            file=sys.stderr,
        )
        return 1

    print(
        "P1 risk evidence reconciliation: OK "
        f"({report['inventory']['total_obligation_count']} obligations; "
        f"{report['resolved_count']} resolved; "
        f"{report['unresolved_blocking_count']} blocking unresolved; "
        f"{report['unclassified_count']} unclassified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
