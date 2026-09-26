#!/usr/bin/env python3
"""Verify Stage-0 AI dependency closure and promotion ordering.

This verifier is intentionally source-only. It does not infer that a GitHub
workflow passed. Instead it proves that closure metadata, dedicated exact-head
workflow definitions, independent verifiers, and the Stage-1 dependency graph
are mutually consistent before any gap can be promoted to closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION = Path("machine/ai_app_construction.json")
EVIDENCE = Path("machine/ai_closure_evidence.json")
HANDOFF = Path("machine/ai_implementation_handoff.json")

PREREQUISITES = (
    "gap-governance-registry",
    "gap-cost-admission",
    "gap-provider-surface-convergence",
)
TOOL_RUNTIME_GAP = "gap-tool-runtime-convergence"

CLOSURE_SURFACES: dict[str, dict[str, str]] = {
    "gap-governance-registry": {
        "workflow": ".github/workflows/governance-closure.yml",
        "workflow_name": "Governance Closure Gate",
        "verifier": "scripts/verify_governance_closure.py",
        "verifier_identity": "independent-governance-v1",
    },
    "gap-cost-admission": {
        "workflow": ".github/workflows/cost-admission-closure.yml",
        "workflow_name": "Cost Admission Closure Gate",
        "verifier": "scripts/verify_cost_admission_closure.py",
        "verifier_identity": "independent-cost-admission-v1",
    },
    "gap-provider-surface-convergence": {
        "workflow": ".github/workflows/provider-surface-closure.yml",
        "workflow_name": "Provider Surface Closure Gate",
        "verifier": "scripts/verify_provider_surface_closure.py",
        "verifier_identity": "independent-provider-surface-v1",
    },
    TOOL_RUNTIME_GAP: {
        "workflow": ".github/workflows/tool-runtime-closure.yml",
        "workflow_name": "Tool Runtime Closure Gate",
        "verifier": "scripts/verify_tool_runtime_closure.py",
        "verifier_identity": "independent-tool-runtime-v1",
    },
}

EXACT_HEAD_TOKEN = "github.event.pull_request.head.sha || github.sha"


class VerificationError(RuntimeError):
    """Dependency-closure verification failed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _indexed(
    values: object,
    key: str,
    *,
    source: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(values, list):
        errors.append(f"{source} must be a list")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            errors.append(f"{source}[{index}] must be an object")
            continue
        raw = item.get(key)
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"{source}[{index}].{key} must be non-empty")
            continue
        identity = raw.strip()
        if identity in result:
            errors.append(f"{source} contains duplicate {key}: {identity}")
            continue
        result[identity] = item
    return result


def _verify_closure_surfaces(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for gap_id, surface in CLOSURE_SURFACES.items():
        workflow_rel = surface["workflow"]
        verifier_rel = surface["verifier"]
        workflow_path = root / workflow_rel
        verifier_path = root / verifier_rel
        if not workflow_path.is_file():
            errors.append(f"{gap_id} closure workflow is missing: {workflow_rel}")
            continue
        if not verifier_path.is_file():
            errors.append(f"{gap_id} independent verifier is missing: {verifier_rel}")
            continue

        workflow = _read_text(workflow_path)
        verifier = _read_text(verifier_path)
        if f"name: {surface['workflow_name']}" not in workflow:
            errors.append(
                f"{gap_id} workflow lost canonical name: {surface['workflow_name']}"
            )
        if EXACT_HEAD_TOKEN not in workflow:
            errors.append(f"{gap_id} workflow is not bound to exact PR head")
        if "persist-credentials: false" not in workflow:
            errors.append(f"{gap_id} workflow checkout must disable credentials")
        if surface["verifier_identity"] not in verifier:
            errors.append(
                f"{gap_id} verifier lost identity: {surface['verifier_identity']}"
            )
        if "GITHUB_SHA" not in verifier:
            errors.append(f"{gap_id} verifier does not bind evidence to GITHUB_SHA")

        digests[workflow_rel] = hashlib.sha256(
            workflow.encode("utf-8")
        ).hexdigest()
        digests[verifier_rel] = hashlib.sha256(
            verifier.encode("utf-8")
        ).hexdigest()
    return digests


def _verify_machine_consistency(
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    construction = _load_json(root / CONSTRUCTION)
    evidence = _load_json(root / EVIDENCE)
    handoff = _load_json(root / HANDOFF)

    gaps = _indexed(
        construction.get("gap_register"),
        "id",
        source="construction.gap_register",
        errors=errors,
    )
    evidence_entries = _indexed(
        evidence.get("entries"),
        "gap",
        source="closure_evidence.entries",
        errors=errors,
    )
    handoff_entries = _indexed(
        handoff.get("entries"),
        "gap",
        source="implementation_handoff.entries",
        errors=errors,
    )

    relevant = (*PREREQUISITES, TOOL_RUNTIME_GAP)
    statuses: dict[str, str] = {}
    readiness: dict[str, dict[str, Any]] = {}

    for gap_id in relevant:
        gap = gaps.get(gap_id)
        evidence_entry = evidence_entries.get(gap_id)
        handoff_entry = handoff_entries.get(gap_id)
        if gap is None:
            errors.append(f"construction is missing {gap_id}")
            continue
        if evidence_entry is None:
            errors.append(f"closure evidence is missing {gap_id}")
            continue
        if handoff_entry is None:
            errors.append(f"implementation handoff is missing {gap_id}")
            continue

        status = str(gap.get("status") or "")
        statuses[gap_id] = status
        if status not in {"open", "closed"}:
            errors.append(f"{gap_id} has invalid construction status: {status!r}")

        evidence_status = str(evidence_entry.get("gap_status") or "")
        if evidence_status != status:
            errors.append(
                f"{gap_id} construction/evidence status mismatch: "
                f"{status!r} != {evidence_status!r}"
            )

        closure_decision = str(evidence_entry.get("closure_decision") or "")
        if status == "closed" and closure_decision != "closed":
            errors.append(
                f"{gap_id} is closed but closure_decision is not closed"
            )
        if status == "open" and closure_decision == "closed":
            errors.append(
                f"{gap_id} is open but closure_decision is already closed"
            )

        blockers = evidence_entry.get("blockers")
        outstanding = evidence_entry.get("outstanding_evidence")
        if not isinstance(blockers, list):
            errors.append(f"{gap_id} blockers must be a list")
            blockers = []
        if not isinstance(outstanding, list):
            errors.append(f"{gap_id} outstanding_evidence must be a list")
            outstanding = []
        if status == "closed" and (blockers or outstanding):
            errors.append(
                f"{gap_id} is closed with unresolved blockers/evidence"
            )

        implementation_status = str(
            handoff_entry.get("implementation_status") or ""
        )
        remaining = handoff_entry.get("remaining")
        if not isinstance(remaining, list):
            errors.append(f"{gap_id} handoff remaining must be a list")
            remaining = []
        if status == "closed" and remaining:
            errors.append(f"{gap_id} is closed with handoff remaining work")

        readiness[gap_id] = {
            "status": status,
            "closure_decision": closure_decision,
            "implementation_status": implementation_status,
            "blocker_count": len(blockers),
            "outstanding_count": len(outstanding),
            "remaining_count": len(remaining),
        }

    tool = handoff_entries.get(TOOL_RUNTIME_GAP)
    if tool is not None:
        depends = tool.get("depends_on")
        if not isinstance(depends, list):
            errors.append("tool-runtime depends_on must be a list")
        elif set(map(str, depends)) != set(PREREQUISITES):
            errors.append(
                "tool-runtime dependency graph does not match Stage-0 prerequisites"
            )

    if statuses.get(TOOL_RUNTIME_GAP) == "closed":
        not_closed = [
            gap_id
            for gap_id in PREREQUISITES
            if statuses.get(gap_id) != "closed"
        ]
        if not_closed:
            errors.append(
                "tool-runtime is closed before prerequisites: "
                + ", ".join(sorted(not_closed))
            )

    return {
        "statuses": statuses,
        "readiness": readiness,
    }


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    surfaces = _verify_closure_surfaces(root, errors)
    machine = _verify_machine_consistency(root, errors)

    prerequisite_status = {
        gap_id: machine.get("statuses", {}).get(gap_id, "missing")
        for gap_id in PREREQUISITES
    }
    prerequisites_closed = all(
        status == "closed" for status in prerequisite_status.values()
    )

    return {
        "schema_version": 1,
        "verifier": "ai-dependency-closure-v1",
        "head_sha": os.environ.get("GITHUB_SHA", "").strip() or "unknown",
        "prerequisites": list(PREREQUISITES),
        "prerequisite_status": prerequisite_status,
        "prerequisites_closed": prerequisites_closed,
        "tool_runtime_status": machine.get("statuses", {}).get(
            TOOL_RUNTIME_GAP,
            "missing",
        ),
        "readiness": machine.get("readiness", {}),
        "closure_surface_digests": surfaces,
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
        print(f"ai-dependency-closure: rejected: {exc}", file=sys.stderr)
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
        print("ai-dependency-closure: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "ai-dependency-closure: OK "
        f"(prerequisites_closed={receipt['prerequisites_closed']}, "
        f"surfaces={len(receipt['closure_surface_digests'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
