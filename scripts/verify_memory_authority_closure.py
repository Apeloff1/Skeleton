#!/usr/bin/env python3
"""Independent durable-memory authority closure verifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
GAP_ID = "gap-memory-durable-authority"

SOURCE_TOKENS = {
    "skeleton/contracts/memory_record.py": (
        "class MemoryWriteProposal",
        "class MemoryRecord",
    ),
    "skeleton/persistence/memory_repository.py": (
        "class SQLiteMemoryRepository",
        "class MongoMemoryRepository",
        "MemoryProjectionEvent",
        "pending_projection_events",
    ),
    "skeleton/memory/writeback.py": (
        "class GovernedMemoryWriter",
        "class AsyncGovernedMemoryWriter",
    ),
    "skeleton/memory/projection.py": (
        "class ProjectionState",
        "DEGRADED",
        "rebuild",
        "delete",
    ),
    "skeleton/testing/test_memory_repository.py": ("def test_",),
    "skeleton/testing/test_mongo_memory_repository.py": ("test_",),
    "skeleton/testing/test_memory_writeback.py": ("test_",),
    "skeleton/testing/test_memory_projection.py": ("test_",),
}

EXPECTED_DEPENDENCIES = {
    "gap-state-authority-convergence",
    "gap-governance-registry",
}


class VerificationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def find_entry(items: object, key: str, value: str) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    return next(
        (
            item
            for item in items
            if isinstance(item, dict) and item.get(key) == value
        ),
        None,
    )


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    digests: dict[str, str] = {}

    for rel, tokens in SOURCE_TOKENS.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"missing memory closure boundary: {rel}")
            continue
        source = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost memory closure token: {token}")
        digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    construction = load_json(root / "machine/ai_app_construction.json")
    handoff = load_json(root / "machine/ai_implementation_handoff.json")
    closure = load_json(root / "machine/ai_closure_evidence.json")

    gap = find_entry(construction.get("gap_register"), "id", GAP_ID)
    hand = find_entry(handoff.get("entries"), "gap", GAP_ID)
    evidence = find_entry(closure.get("entries"), "gap", GAP_ID)
    blueprint = construction.get("memory_runtime_blueprint")

    if gap is None or gap.get("status") != "closed":
        errors.append("durable-memory construction gap is not closed")
    if not isinstance(blueprint, dict):
        errors.append("memory_runtime_blueprint is missing")
    else:
        if blueprint.get("gap") != GAP_ID:
            errors.append("memory blueprint gap binding is invalid")
        if blueprint.get("status") not in {"complete", "closed"}:
            errors.append("memory blueprint is not complete")
        if blueprint.get("remaining_surfaces") not in ([], None):
            errors.append("memory blueprint still has remaining surfaces")

    if hand is None:
        errors.append("durable-memory handoff is missing")
    else:
        if hand.get("implementation_status") != "closed":
            errors.append("durable-memory handoff is not closed")
        if set(hand.get("depends_on") or []) != EXPECTED_DEPENDENCIES:
            errors.append("durable-memory dependency graph mismatch")
        if hand.get("remaining") not in ([], None):
            errors.append("durable-memory handoff still has remaining work")

    if evidence is None:
        errors.append("durable-memory closure evidence is missing")
    else:
        for field in ("gap_status", "implementation_state", "closure_decision"):
            if evidence.get(field) != "closed":
                errors.append(f"durable-memory {field} is not closed")
        if evidence.get("outstanding_evidence") not in ([], None):
            errors.append("durable-memory evidence is still outstanding")
        if evidence.get("blockers") not in ([], None):
            errors.append("durable-memory closure still has blockers")
        present = evidence.get("evidence_present")
        if not isinstance(present, list) or len(present) < 8:
            errors.append("durable-memory executable evidence is incomplete")

    return {
        "schema_version": 1,
        "verifier": "independent-memory-authority-v1",
        "gap_id": GAP_ID,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "boundary_digests": digests,
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
        print(f"memory-authority-closure: rejected: {exc}", file=sys.stderr)
        return 1
    if args.evidence_out:
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["valid"]:
        print("memory-authority-closure: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f" - {error}", file=sys.stderr)
        return 1
    print(
        "memory-authority-closure: OK "
        f"(boundaries={len(receipt['boundary_digests'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
