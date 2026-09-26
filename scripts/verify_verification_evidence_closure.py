#!/usr/bin/env python3
"""Independent verification-evidence closure verifier.

This verifier does not import the canonical verification runtime. It audits
observable verification contracts, deterministic evidence/postcondition policy,
semantic-provider isolation, durable verification-receipt persistence, AI-tree
mirror parity, and the declared dependency graph directly from repository
source and machine contracts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]

BOUNDARIES: dict[str, tuple[str, ...]] = {
    "skeleton/contracts/verification.py": (
        "class VerificationClaim",
        "class EvidenceReference",
        "class PostconditionObservation",
        "class VerificationCheck",
        "class VerificationReceipt",
        "claim_digest",
        "supporting_evidence_ids",
        "postcondition_observation_ids",
        "policy_satisfied",
    ),
    "skeleton/intelligence/verification_policy.py": (
        "select_verification_policy",
        "allow_model_only_evidence=False",
        "min_independent_origins",
        "require_postcondition",
        "model_origin_requires_external_evidence",
    ),
    "skeleton/intelligence/verification_runtime.py": (
        "class VerificationRuntime",
        "class SemanticVerificationRuntime",
        "materialize_verification_receipt",
        "authoritative_support_missing",
        "independent_verification_required",
        "postcondition_observation_required",
        "semantic_repair_budget_exhausted",
        "repaired_claim_requires_citation_rebinding",
        "ProviderAdapter",
    ),
    "skeleton/persistence/execution_repository.py": (
        "ai_verification_receipt",
        "remember_verification_receipt",
        "verification_receipt(",
        "verification_receipts_for_execution",
        "verification receipts",
    ),
    "skeleton/intelligence/execution_runtime.py": (
        "materialize_verification_receipt",
        "remember_verification_receipt",
        "verification-receipt",
        "verification_receipt=",
        "_verify_and_finalize",
    ),
    "skeleton/skills/verification.py": (
        "observe_tool_postcondition",
        "ToolPostconditionError",
        "ToolExecutionReceipt",
    ),
}

MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "skeleton/contracts/verification.py",
        "skeleton/ai/runtime/contracts/verification.py",
    ),
    (
        "skeleton/intelligence/verification_policy.py",
        "skeleton/ai/runtime/intelligence/verification_policy.py",
    ),
    (
        "skeleton/intelligence/verification_runtime.py",
        "skeleton/ai/runtime/intelligence/verification_runtime.py",
    ),
    (
        "skeleton/persistence/execution_repository.py",
        "skeleton/ai/runtime/persistence/execution_repository.py",
    ),
    (
        "skeleton/intelligence/execution_runtime.py",
        "skeleton/ai/runtime/intelligence/execution_runtime.py",
    ),
    (
        "skeleton/skills/verification.py",
        "skeleton/ai/runtime/skills/verification.py",
    ),
)

EXPECTED_DEPENDENCIES = {
    "gap-context-compiler-convergence",
    "gap-tool-runtime-convergence",
    "gap-provider-interaction-protocol",
}

FORBIDDEN_HIDDEN_REASONING_TOKENS = (
    "chain_of_thought",
    "chain-of-thought",
    "hidden_reasoning",
    "reasoning_text",
)


class VerificationError(RuntimeError):
    """Independent verification-evidence verification failed."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def _verify_boundaries(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"verification boundary is missing: {rel}")
            continue
        source = _read_text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost verification token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()

    contract_source = _read_text(root / "skeleton/contracts/verification.py")
    receipt_start = contract_source.find("class VerificationReceipt")
    if receipt_start >= 0:
        receipt_source = contract_source[receipt_start:]
        for token in FORBIDDEN_HIDDEN_REASONING_TOKENS:
            if token in receipt_source:
                errors.append(
                    "verification receipt contract contains hidden-reasoning field: "
                    + token
                )
    return digests


def _verify_mirrors(root: Path, errors: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        if not source.is_file():
            errors.append(f"canonical mirror source is missing: {source_rel}")
            continue
        if not mirror.is_file():
            errors.append(f"canonical AI mirror is missing: {mirror_rel}")
            continue
        try:
            source_bytes = source.read_bytes()
            mirror_bytes = mirror.read_bytes()
        except OSError as exc:
            errors.append(
                f"cannot verify mirror pair {source_rel} -> {mirror_rel}: "
                + type(exc).__name__
            )
            continue
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        mirror_digest = hashlib.sha256(mirror_bytes).hexdigest()
        rows.append(
            {
                "source": source_rel,
                "mirror": mirror_rel,
                "source_digest": source_digest,
                "mirror_digest": mirror_digest,
            }
        )
        if source_bytes != mirror_bytes:
            errors.append(
                f"canonical AI mirror drift: {source_rel} != {mirror_rel}"
            )
    return rows


def _find_entry(payload: dict[str, Any], gap_id: str) -> dict[str, Any] | None:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return None
    return next(
        (
            item
            for item in entries
            if isinstance(item, dict) and item.get("gap") == gap_id
        ),
        None,
    )


def _verify_machine_contracts(root: Path, errors: list[str]) -> dict[str, Any]:
    gap_id = "gap-verification-evidence-contract"
    handoff = _load_json(root / "machine/ai_implementation_handoff.json")
    entry = _find_entry(handoff, gap_id)
    if entry is None:
        errors.append("verification handoff entry is missing")
        return {}

    deps = entry.get("depends_on")
    if not isinstance(deps, list):
        errors.append("verification depends_on must be a list")
        deps = []
    actual = {str(item) for item in deps}
    if actual != EXPECTED_DEPENDENCIES:
        errors.append(
            "verification dependency graph mismatch: "
            + ", ".join(sorted(actual))
        )

    if entry.get("implementation_status") not in {
        "implementation-complete",
        "closed",
    }:
        errors.append("verification handoff is not implementation-complete")

    closure_gate = str(entry.get("closure_gate") or "")
    for phrase in (
        "immutable observable VerificationReceipt",
        "claims/actions",
        "declared evidence/checks",
    ):
        if phrase not in closure_gate:
            errors.append(
                "verification closure gate lost invariant phrase: " + phrase
            )

    construction = _load_json(root / "machine/ai_app_construction.json")
    gaps = construction.get("gap_register")
    gap_status = "missing"
    dependency_status: dict[str, str] = {}
    if not isinstance(gaps, list):
        errors.append("construction gap_register must be a list")
    else:
        for item in gaps:
            if not isinstance(item, dict):
                continue
            current_id = str(item.get("id") or "")
            status = str(item.get("status") or "")
            if current_id == gap_id:
                gap_status = status
            if current_id in EXPECTED_DEPENDENCIES:
                dependency_status[current_id] = status

    missing = sorted(EXPECTED_DEPENDENCIES - set(dependency_status))
    if missing:
        errors.append(
            "verification dependency statuses missing: "
            + ", ".join(missing)
        )

    blueprint = construction.get("verification_runtime_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("verification_runtime_blueprint is missing")
    else:
        if blueprint.get("status") not in {
            "implemented-pending-closure",
            "closed",
        }:
            errors.append(
                "verification runtime blueprint is not implemented-pending-closure"
            )

    if gap_status == "closed":
        open_dependencies = sorted(
            dep
            for dep in EXPECTED_DEPENDENCIES
            if dependency_status.get(dep) != "closed"
        )
        if open_dependencies:
            errors.append(
                "closed verification gap has non-closed dependencies: "
                + ", ".join(open_dependencies)
            )
    elif gap_status != "open":
        errors.append("verification construction status is invalid")

    entry["_verified_dependency_status"] = {
        dep: dependency_status.get(dep, "missing")
        for dep in sorted(EXPECTED_DEPENDENCIES)
    }
    entry["_verified_gap_status"] = gap_status
    return entry


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    boundary_digests = _verify_boundaries(root, errors)
    mirrors = _verify_mirrors(root, errors)
    handoff = _verify_machine_contracts(root, errors)
    handoff_digest = hashlib.sha256(
        json.dumps(
            handoff,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "verifier": "independent-verification-evidence-v1",
        "head_sha": os.environ.get("GITHUB_SHA", "").strip() or "unknown",
        "boundary_digests": boundary_digests,
        "mirror_pairs": mirrors,
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "dependency_status": dict(
            handoff.get("_verified_dependency_status") or {}
        ),
        "gap_status": handoff.get("_verified_gap_status"),
        "handoff_digest": handoff_digest,
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        print(f"independent-verification-evidence: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("independent-verification-evidence: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "independent-verification-evidence: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
