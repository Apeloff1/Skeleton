#!/usr/bin/env python3
"""Independent governance closure verifier.

This verifier deliberately does not import the governance runtime. It validates
the machine governance blueprint, authoritative state-topology declaration,
production boundary ownership tokens, and canonical AI-tree mirror parity from
repository source bytes only.
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
CONSTRUCTION = Path("machine/ai_app_construction.json")
STATE_TOPOLOGY = Path("machine/state_topology.json")

BOUNDARIES: dict[str, tuple[str, ...]] = {
    "skeleton/vault/governance_registry.py": (
        "GovernanceRegistry",
        "DataLifecycleRegistry",
        "GovernanceAuditTimeline",
        "register",
        "reconcile",
    ),
    "skeleton/vault/data_lifecycle.py": (
        "DataLifecycleRegistry",
        "deletion",
        "retention",
        "export",
        "tenant",
    ),
    "skeleton/vault/governance_audit.py": (
        "GovernanceAuditTimeline",
        "register",
        "reconcile",
        "deletion",
        "export",
    ),
    "skeleton/vault/lifecycle_adapters.py": (
        "Lifecycle",
        "deletion",
        "export",
        "tenant",
    ),
    "skeleton/memory/writeback.py": (
        "GovernanceRegistry",
        "retention",
        "tenant",
    ),
    "skeleton/memory/projection.py": (
        "GovernanceRegistry",
        "register",
        "deletion",
        "tenant",
    ),
    "skeleton/retrieval/governance.py": (
        "GovernanceRegistry",
        "register",
        "tenant",
        "retention",
    ),
    "skeleton/artifact_plane/governance.py": (
        "GovernanceRegistry",
        "register",
        "reconcile",
        "tenant",
        "retention",
    ),
    "skeleton/api/server.py": (
        "GovernanceRegistry",
        "GovernanceAuditTimeline",
        "LifecycleExecutor",
    ),
    "backend/core/conversations.py": (
        "register",
        "tenant",
        "deletion",
        "export",
    ),
    "backend/core/route_privacy.py": (
        "privacy",
        "provider",
        "tool",
        "route",
    ),
    "backend/core/gameforge_artifact_builder.py": (
        "GovernedArtifact",
        "tenant",
        "retention",
    ),
}

MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "skeleton/vault/governance_registry.py",
        "skeleton/ai/runtime/vault/governance_registry.py",
    ),
    (
        "skeleton/vault/data_lifecycle.py",
        "skeleton/ai/runtime/vault/data_lifecycle.py",
    ),
    (
        "skeleton/vault/governance_audit.py",
        "skeleton/ai/runtime/vault/governance_audit.py",
    ),
    (
        "skeleton/vault/lifecycle_adapters.py",
        "skeleton/ai/runtime/vault/lifecycle_adapters.py",
    ),
    (
        "skeleton/memory/writeback.py",
        "skeleton/ai/runtime/memory/writeback.py",
    ),
    (
        "skeleton/memory/projection.py",
        "skeleton/ai/runtime/memory/projection.py",
    ),
    (
        "skeleton/retrieval/governance.py",
        "skeleton/ai/runtime/retrieval/governance.py",
    ),
    (
        "skeleton/artifact_plane/governance.py",
        "skeleton/ai/runtime/artifact_plane/governance.py",
    ),
    (
        "skeleton/api/server.py",
        "skeleton/ai/runtime/api/server.py",
    ),
)

REQUIRED_DECISIONS = {
    "read",
    "write",
    "provider_transfer",
    "tool_transfer",
    "artifact_materialization",
    "memory_commit",
    "retrieval_index",
    "export",
    "delete",
    "retain",
}

REQUIRED_CROSS_PLANE_BINDINGS = {
    "conversation messages",
    "canonical memory",
    "retrieval sources/results",
    "artifact metadata/content",
    "context segments",
    "provider requests",
    "tool arguments/results",
    "verification evidence",
}

REQUIRED_FAIL_CLOSED_PHRASES = (
    "unknown tenant",
    "unknown data class",
    "purpose mismatch",
    "privacy ceiling",
    "cross-tenant",
    "expired/deleting",
)


class VerificationError(RuntimeError):
    """Independent governance verification failed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read source {path}") from exc


def _verify_machine_contract(root: Path, errors: list[str]) -> dict[str, Any]:
    contract = _load_json(root / CONSTRUCTION)
    gaps = contract.get("gap_register")
    if not isinstance(gaps, list):
        errors.append("gap_register must be a list")
        return contract
    gap = next(
        (
            item
            for item in gaps
            if isinstance(item, dict)
            and item.get("id") == "gap-governance-registry"
        ),
        None,
    )
    if gap is None:
        errors.append("gap-governance-registry is missing from gap_register")
    elif gap.get("status") not in {"open", "closed"}:
        errors.append("gap-governance-registry has invalid status")

    blueprint = contract.get("governance_runtime_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("governance_runtime_blueprint must be an object")
        return contract

    if blueprint.get("canonical_owner") != "skeleton/vault":
        errors.append("governance canonical_owner is not skeleton/vault")

    decisions = blueprint.get("decisions")
    if not isinstance(decisions, list):
        errors.append("governance decisions must be a list")
    else:
        missing = sorted(REQUIRED_DECISIONS - set(map(str, decisions)))
        if missing:
            errors.append(
                "governance blueprint missing decisions: " + ", ".join(missing)
            )

    bindings = blueprint.get("cross_plane_bindings")
    if not isinstance(bindings, list):
        errors.append("governance cross_plane_bindings must be a list")
    else:
        missing = sorted(
            REQUIRED_CROSS_PLANE_BINDINGS - set(map(str, bindings))
        )
        if missing:
            errors.append(
                "governance blueprint missing cross-plane bindings: "
                + ", ".join(missing)
            )

    fail_closed = blueprint.get("fail_closed")
    if not isinstance(fail_closed, list):
        errors.append("governance fail_closed must be a list")
    else:
        joined = "\n".join(str(item) for item in fail_closed).lower()
        for phrase in REQUIRED_FAIL_CLOSED_PHRASES:
            if phrase not in joined:
                errors.append(
                    "governance blueprint lost fail-closed invariant: " + phrase
                )

    receipt = blueprint.get("decision_receipt")
    if not isinstance(receipt, dict):
        errors.append("governance decision_receipt must be an object")
    else:
        fields = receipt.get("required_fields")
        if not isinstance(fields, list):
            errors.append("governance decision receipt fields must be a list")
        else:
            required = {
                "decision_id",
                "operation_id",
                "tenant_id",
                "action",
                "resource_refs",
                "allowed",
                "reason_codes",
                "policy_version",
                "decided_at",
            }
            missing = sorted(required - set(map(str, fields)))
            if missing:
                errors.append(
                    "governance decision receipt missing fields: "
                    + ", ".join(missing)
                )

    lifecycle = blueprint.get("lifecycle")
    if not isinstance(lifecycle, dict):
        errors.append("governance lifecycle contract must be an object")
    else:
        for action in ("deletion", "export", "retention"):
            values = lifecycle.get(action)
            if not isinstance(values, list) or not values:
                errors.append(
                    f"governance lifecycle {action} contract is missing"
                )
    return contract


def _verify_state_topology(root: Path, errors: list[str]) -> dict[str, Any]:
    topology = _load_json(root / STATE_TOPOLOGY)
    serialized = json.dumps(
        topology,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    for token in (
        "governance-lifecycle-sqlite",
        "authoritative lifecycle metadata",
        "skeleton/vault/data_lifecycle.py",
        "skeleton/vault/governance_registry.py",
        "skeleton/vault/lifecycle_adapters.py",
        "skeleton/api/server.py",
    ):
        if token not in serialized:
            errors.append("state topology lost governance authority token: " + token)
    return topology


def _verify_boundaries(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"governance boundary is missing: {rel}")
            continue
        source = _read_text(path)
        lowered = source.lower()
        for token in tokens:
            if token.lower() not in lowered:
                errors.append(f"{rel} lost governance token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()
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


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    contract = _verify_machine_contract(root, errors)
    topology = _verify_state_topology(root, errors)
    boundary_digests = _verify_boundaries(root, errors)
    mirrors = _verify_mirrors(root, errors)

    blueprint = contract.get("governance_runtime_blueprint")
    blueprint_digest = hashlib.sha256(
        json.dumps(
            blueprint if isinstance(blueprint, dict) else {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    topology_digest = hashlib.sha256(
        json.dumps(
            topology,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "verifier": "independent-governance-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown",
        "blueprint_digest": blueprint_digest,
        "state_topology_digest": topology_digest,
        "boundary_digests": boundary_digests,
        "mirror_pairs": mirrors,
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
        print(f"independent-governance: rejected: {exc}", file=sys.stderr)
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
        print("independent-governance: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "independent-governance: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
