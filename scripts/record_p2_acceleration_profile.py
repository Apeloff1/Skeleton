#!/usr/bin/env python3
"""Safely record P2 accelerator profile evidence into machine policy."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from skeleton.native.profiling import source_identity
from skeleton.native.selection import (
    AccelerationSelectionError,
    ProfileEvidence,
    SelectionDecision,
    evaluate_candidate,
    policy_from_mapping,
)


ROOT = Path(__file__).resolve().parents[1]


class ReceiptIngestionError(RuntimeError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptIngestionError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ReceiptIngestionError(f"non-finite JSON token rejected: {value}")


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except FileNotFoundError as exc:
        raise ReceiptIngestionError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReceiptIngestionError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReceiptIngestionError(f"{label} must contain a JSON object")
    return payload


def _evidence_from_mapping(raw: Mapping[str, Any]) -> ProfileEvidence:
    try:
        return ProfileEvidence(**dict(raw))
    except (TypeError, ValueError) as exc:
        raise ReceiptIngestionError(f"invalid profile receipt: {exc}") from exc


def _candidate(policy: Mapping[str, Any], candidate_id: str) -> dict[str, Any]:
    candidates = policy.get("candidates")
    if not isinstance(candidates, list):
        raise ReceiptIngestionError("policy candidates must be a list")
    matches = [
        item for item in candidates
        if isinstance(item, dict) and item.get("id") == candidate_id
    ]
    if len(matches) != 1:
        raise ReceiptIngestionError(
            f"expected exactly one policy candidate {candidate_id!r}"
        )
    return matches[0]


def _all_receipt_ids(policy: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    candidates = policy.get("candidates")
    if not isinstance(candidates, list):
        raise ReceiptIngestionError("policy candidates must be a list")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ReceiptIngestionError("policy candidate must be an object")
        evidence = candidate.get("profile_evidence")
        if not isinstance(evidence, list):
            raise ReceiptIngestionError(
                f"{candidate.get('id')} profile_evidence must be a list"
            )
        for row in evidence:
            if not isinstance(row, dict):
                raise ReceiptIngestionError("stored profile receipt must be an object")
            evidence_id = row.get("evidence_id")
            if not isinstance(evidence_id, str) or not evidence_id:
                raise ReceiptIngestionError("stored profile receipt lacks evidence_id")
            if evidence_id in ids:
                raise ReceiptIngestionError(
                    f"duplicate stored profile evidence id: {evidence_id}"
                )
            ids.add(evidence_id)
    return ids


def _decision(
    policy: Mapping[str, Any],
    candidate: Mapping[str, Any],
    evidence: list[ProfileEvidence],
    *,
    root: Path,
    current_source_identity: str,
) -> SelectionDecision:
    try:
        selection_policy = policy_from_mapping(policy["selection_policy"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReceiptIngestionError(f"invalid selection policy: {exc}") from exc

    reference_paths = candidate.get("reference_paths")
    if not isinstance(reference_paths, list) or not reference_paths:
        raise ReceiptIngestionError("candidate requires reference_paths")
    reference_available = all((root / str(item)).exists() for item in reference_paths)

    crash_risk = candidate.get("crash_risk")
    isolation_satisfied = (
        crash_risk == "low"
        or candidate.get("isolation") == "subprocess"
    )
    protocol_compatible = (
        candidate.get("plane") != "jvm"
        or candidate.get("protocol") == "skeleton.acceleration.rpc@1.0"
    )
    try:
        return evaluate_candidate(
            candidate_id=str(candidate["id"]),
            current_source_identity=current_source_identity,
            reference_available=reference_available,
            isolation_satisfied=isolation_satisfied,
            protocol_compatible=protocol_compatible,
            evidence=evidence,
            policy=selection_policy,
        )
    except (KeyError, AccelerationSelectionError, TypeError, ValueError) as exc:
        raise ReceiptIngestionError(f"selection evaluation failed: {exc}") from exc


def apply_receipt(
    policy: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    root: Path = ROOT,
    activate: bool = False,
) -> tuple[dict[str, Any], SelectionDecision]:
    if not isinstance(activate, bool):
        raise ReceiptIngestionError("activate must be boolean")
    updated = deepcopy(dict(policy))
    evidence = _evidence_from_mapping(receipt)
    candidate = _candidate(updated, evidence.candidate_id)

    identity_paths = candidate.get("source_identity_paths")
    if not isinstance(identity_paths, list) or not identity_paths:
        raise ReceiptIngestionError("candidate requires source_identity_paths")
    try:
        current_identity = source_identity(root, identity_paths)
    except Exception as exc:
        raise ReceiptIngestionError(f"source identity calculation failed: {exc}") from exc
    if evidence.source_identity != current_identity:
        raise ReceiptIngestionError(
            "profile receipt source identity is stale or mismatched"
        )

    if evidence.evidence_id in _all_receipt_ids(updated):
        raise ReceiptIngestionError(
            f"duplicate profile evidence id: {evidence.evidence_id}"
        )

    stored = candidate.get("profile_evidence")
    if not isinstance(stored, list):
        raise ReceiptIngestionError("candidate profile_evidence must be a list")
    stored.append(asdict(evidence))

    evidence_objects = [_evidence_from_mapping(item) for item in stored]
    decision = _decision(
        updated,
        candidate,
        evidence_objects,
        root=root,
        current_source_identity=current_identity,
    )

    if activate and not decision.qualified:
        raise ReceiptIngestionError(
            "activation rejected; non-compensable gates failed: "
            + ",".join(decision.reason_codes)
        )

    if decision.qualified:
        candidate["state"] = (
            "profile_selected_unpromoted"
            if activate
            else "evidence_qualified_unpromoted"
        )
        candidate["automatic_selection"] = bool(activate)
    else:
        candidate["state"] = "candidate_unpromoted"
        candidate["automatic_selection"] = False

    candidate["selection_decision"] = {
        "qualified": decision.qualified,
        "route": decision.route,
        "effective_route": (
            "accelerated"
            if decision.qualified and activate
            else "reference"
        ),
        "reason_codes": list(decision.reason_codes),
        "worst_speedup": decision.worst_speedup,
        "evidence_ids": list(decision.evidence_ids),
        "source_identity": current_identity,
    }
    return updated, decision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--policy",
        default="machine/acceleration_policy.json",
    )
    parser.add_argument("--output")
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()

    if args.output and args.in_place:
        parser.error("--output and --in-place are mutually exclusive")

    policy_path = (ROOT / args.policy).resolve()
    try:
        policy_path.relative_to(ROOT.resolve())
    except ValueError:
        print(
            "P2 acceleration receipt: FAIL: policy path must remain inside the repository",
            file=sys.stderr,
        )
        return 1
    receipt_path = Path(args.receipt).resolve()
    try:
        policy = _load_object(policy_path, label="acceleration policy")
        receipt = _load_object(receipt_path, label="profile receipt")
        updated, decision = apply_receipt(
            policy,
            receipt,
            root=ROOT,
            activate=args.activate,
        )
    except ReceiptIngestionError as exc:
        print(f"P2 acceleration receipt: FAIL: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(
        updated,
        indent=2,
        sort_keys=False,
        allow_nan=False,
    ) + "\n"
    if args.in_place:
        policy_path.write_text(payload, encoding="utf-8")
    elif args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)

    print(
        json.dumps(
            {
                "candidate_id": decision.candidate_id,
                "qualified": decision.qualified,
                "route": decision.route,
                "reason_codes": list(decision.reason_codes),
                "activated": bool(args.activate and decision.qualified),
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
