#!/usr/bin/env python3
"""Independent final AI masterplan closure verifier.

This verifier is intentionally source-only. It does not import product runtime
modules and does not infer that a GitHub workflow passed. It proves that the
canonical construction, handoff, closure-evidence, blueprint, and dependency
contracts all agree that the declared AI masterplan closure graph is closed.
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
HANDOFF = Path("machine/ai_implementation_handoff.json")
EVIDENCE = Path("machine/ai_closure_evidence.json")

EXPECTED_GAPS = (
    "gap-state-authority-convergence",
    "gap-governance-registry",
    "gap-cost-admission",
    "gap-provider-surface-convergence",
    "gap-conversation-state-authority",
    "gap-memory-durable-authority",
    "gap-tool-runtime-convergence",
    "gap-context-compiler-convergence",
    "gap-provider-interaction-protocol",
    "gap-verification-evidence-contract",
    "gap-cognitive-execution-loop",
    "gap-engine-application-execution-boundary",
    "gap-streaming-protocol",
    "gap-e2e-golden-journeys",
)


class VerificationError(RuntimeError):
    """Final closure verification failed."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def _index(
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


def _blueprints(
    construction: Mapping[str, Any],
    errors: list[str],
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    result: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for key, value in construction.items():
        if not isinstance(value, dict):
            continue
        gap = value.get("gap")
        if not isinstance(gap, str) or not gap.startswith("gap-"):
            continue
        result.setdefault(gap, []).append((key, value))

    for gap_id in EXPECTED_GAPS:
        matches = result.get(gap_id, [])
        if not matches:
            errors.append(f"{gap_id} has no associated blueprint/contract")
        elif len(matches) > 1:
            names = ", ".join(name for name, _ in matches)
            errors.append(f"{gap_id} has multiple blueprint owners: {names}")
    return result


def _verify_closed_record(
    gap_id: str,
    construction_entry: Mapping[str, Any],
    handoff_entry: Mapping[str, Any],
    evidence_entry: Mapping[str, Any],
    blueprint_matches: list[tuple[str, dict[str, Any]]],
    errors: list[str],
) -> dict[str, Any]:
    status = str(construction_entry.get("status") or "")
    if status != "closed":
        errors.append(f"{gap_id} construction status is not closed: {status!r}")

    implementation_status = str(handoff_entry.get("implementation_status") or "")
    if implementation_status != "closed":
        errors.append(
            f"{gap_id} implementation_status is not closed: "
            f"{implementation_status!r}"
        )

    evidence_status = str(evidence_entry.get("gap_status") or "")
    if evidence_status != "closed":
        errors.append(f"{gap_id} evidence gap_status is not closed: {evidence_status!r}")

    closure_decision = str(evidence_entry.get("closure_decision") or "")
    if closure_decision != "closed":
        errors.append(
            f"{gap_id} closure_decision is not closed: {closure_decision!r}"
        )

    for field, record in (
        ("remaining", handoff_entry),
        ("outstanding_evidence", evidence_entry),
        ("blockers", evidence_entry),
    ):
        value = record.get(field)
        if not isinstance(value, list):
            errors.append(f"{gap_id} {field} must be a list")
        elif value:
            errors.append(f"{gap_id} is closed with non-empty {field}")

    blueprint_name = ""
    blueprint_status = "missing"
    if len(blueprint_matches) == 1:
        blueprint_name, blueprint = blueprint_matches[0]
        blueprint_status = str(blueprint.get("status") or "")
        if blueprint_status != "closed":
            errors.append(
                f"{gap_id} blueprint {blueprint_name} is not closed: "
                f"{blueprint_status!r}"
            )
        for field in ("remaining", "remaining_surfaces"):
            if field in blueprint:
                value = blueprint.get(field)
                if not isinstance(value, list):
                    errors.append(
                        f"{gap_id} blueprint {blueprint_name}.{field} must be a list"
                    )
                elif value:
                    errors.append(
                        f"{gap_id} blueprint {blueprint_name} has non-empty {field}"
                    )

    depends = handoff_entry.get("depends_on", [])
    if not isinstance(depends, list):
        errors.append(f"{gap_id} depends_on must be a list")
        depends = []
    dependencies = [str(item) for item in depends]
    unknown = sorted(set(dependencies) - set(EXPECTED_GAPS))
    if unknown:
        errors.append(
            f"{gap_id} has unknown dependencies: " + ", ".join(unknown)
        )

    return {
        "construction_status": status,
        "implementation_status": implementation_status,
        "evidence_status": evidence_status,
        "closure_decision": closure_decision,
        "blueprint": blueprint_name,
        "blueprint_status": blueprint_status,
        "depends_on": dependencies,
    }


def _verify_dependency_graph(
    rows: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for gap_id in EXPECTED_GAPS:
        row = rows.get(gap_id)
        if row is None:
            continue
        for dependency in row.get("depends_on", []):
            edges.append((gap_id, dependency))
            dep = rows.get(dependency)
            if dep is None:
                errors.append(f"{gap_id} dependency is missing: {dependency}")
            elif dep.get("construction_status") != "closed":
                errors.append(
                    f"{gap_id} depends on non-closed gap: {dependency}"
                )

    adjacency = {
        gap_id: list(rows.get(gap_id, {}).get("depends_on", []))
        for gap_id in EXPECTED_GAPS
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: tuple[str, ...]) -> None:
        if node in visited:
            return
        if node in visiting:
            errors.append(
                "closure dependency graph contains cycle: "
                + " -> ".join((*trail, node))
            )
            return
        visiting.add(node)
        for dependency in adjacency.get(node, []):
            if dependency in adjacency:
                visit(dependency, (*trail, node))
        visiting.remove(node)
        visited.add(node)

    for gap_id in EXPECTED_GAPS:
        visit(gap_id, ())

    return sorted(edges)


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    construction = _load(root / CONSTRUCTION)
    handoff = _load(root / HANDOFF)
    evidence = _load(root / EVIDENCE)

    construction_index = _index(
        construction.get("gap_register"),
        "id",
        source="construction.gap_register",
        errors=errors,
    )
    handoff_index = _index(
        handoff.get("entries"),
        "gap",
        source="implementation_handoff.entries",
        errors=errors,
    )
    evidence_index = _index(
        evidence.get("entries"),
        "gap",
        source="closure_evidence.entries",
        errors=errors,
    )
    blueprint_index = _blueprints(construction, errors)

    rows: dict[str, dict[str, Any]] = {}
    for gap_id in EXPECTED_GAPS:
        c = construction_index.get(gap_id)
        h = handoff_index.get(gap_id)
        e = evidence_index.get(gap_id)
        if c is None:
            errors.append(f"construction is missing {gap_id}")
            continue
        if h is None:
            errors.append(f"implementation handoff is missing {gap_id}")
            continue
        if e is None:
            errors.append(f"closure evidence is missing {gap_id}")
            continue
        rows[gap_id] = _verify_closed_record(
            gap_id,
            c,
            h,
            e,
            blueprint_index.get(gap_id, []),
            errors,
        )

    extra_closed = sorted(
        gap_id
        for gap_id, item in construction_index.items()
        if item.get("status") == "closed" and gap_id not in EXPECTED_GAPS
    )
    dependency_edges = _verify_dependency_graph(rows, errors)

    digests = {}
    for relative in (CONSTRUCTION, HANDOFF, EVIDENCE):
        raw = (root / relative).read_bytes()
        digests[relative.as_posix()] = hashlib.sha256(raw).hexdigest()

    closed_count = sum(
        1
        for gap_id in EXPECTED_GAPS
        if rows.get(gap_id, {}).get("construction_status") == "closed"
        and rows.get(gap_id, {}).get("implementation_status") == "closed"
        and rows.get(gap_id, {}).get("evidence_status") == "closed"
        and rows.get(gap_id, {}).get("closure_decision") == "closed"
        and rows.get(gap_id, {}).get("blueprint_status") == "closed"
    )

    return {
        "schema_version": 1,
        "verifier": "ai-masterplan-final-closure-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "expected_gap_count": len(EXPECTED_GAPS),
        "closed_gap_count": closed_count,
        "expected_gaps": list(EXPECTED_GAPS),
        "rows": rows,
        "dependency_edges": [
            {"gap": gap_id, "depends_on": dependency}
            for gap_id, dependency in dependency_edges
        ],
        "extra_closed_gaps": extra_closed,
        "contract_digests": digests,
        "errors": errors,
        "valid": not errors and closed_count == len(EXPECTED_GAPS),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        print(f"ai-masterplan-final-closure: rejected: {exc}", file=sys.stderr)
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
        print("ai-masterplan-final-closure: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "ai-masterplan-final-closure: OK "
        f"(closed={receipt['closed_gap_count']}/"
        f"{receipt['expected_gap_count']}, "
        f"edges={len(receipt['dependency_edges'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
