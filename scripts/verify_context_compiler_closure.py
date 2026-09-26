#!/usr/bin/env python3
"""Independent exact-head verifier for canonical context-compiler convergence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_ID = "independent-context-compiler-v1"

BOUNDARY_FILES = (
    "skeleton/contracts/context.py",
    "skeleton/context/compiler.py",
    "skeleton/context/compaction.py",
    "skeleton/context/policy.py",
    "skeleton/context/instruction_policy.py",
    "backend/core/engine_client.py",
    "scripts/check_context_execution_boundary.py",
    "scripts/check_instruction_policy_boundary.py",
    "tests/test_context_execution_boundary.py",
    "tests/test_instruction_policy_boundary.py",
    "machine/ai_app_construction.json",
    "machine/ai_implementation_handoff.json",
)

MIRROR_PAIRS = (
    (
        "skeleton/context/compiler.py",
        "skeleton/ai/runtime/context/compiler.py",
    ),
    (
        "skeleton/context/compaction.py",
        "skeleton/ai/runtime/context/compaction.py",
    ),
    (
        "skeleton/context/policy.py",
        "skeleton/ai/runtime/context/policy.py",
    ),
    (
        "skeleton/context/sources/tool.py",
        "skeleton/ai/runtime/context/sources/tool.py",
    ),
)

EXPECTED_DEPENDENCIES = {
    "gap-conversation-state-authority",
    "gap-memory-durable-authority",
    "gap-tool-runtime-convergence",
    "gap-governance-registry",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_text(root: Path, relative: str) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"required context boundary is unavailable: {relative}") from exc


def _read_json(root: Path, relative: str) -> dict[str, Any]:
    try:
        value = json.loads(_read_text(root, relative))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"required context contract is invalid JSON: {relative}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"required context contract must be an object: {relative}")
    return value


def _require_tokens(
    text: str,
    tokens: tuple[str, ...],
    *,
    surface: str,
    errors: list[str],
) -> None:
    for token in tokens:
        if token not in text:
            errors.append(f"{surface}: missing required token {token!r}")


def verify(root: Path = ROOT, *, head_sha: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    boundary_digests: dict[str, str] = {}

    for relative in BOUNDARY_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing boundary file: {relative}")
            continue
        boundary_digests[relative] = _sha256(path)

    compiler = _read_text(root, "skeleton/context/compiler.py")
    _require_tokens(
        compiler,
        (
            "class ContextCompiler",
            "project_provider_context",
            "source_snapshot",
            "context_digest",
            "compaction_max_tokens",
            "compacted_to:",
        ),
        surface="context compiler",
        errors=errors,
    )

    contracts = _read_text(root, "skeleton/contracts/context.py")
    _require_tokens(
        contracts,
        (
            "class ContextEnvelope",
            "class ContextSegment",
            "class ContextBudget",
            "ContextTrust",
            "ContextKind",
        ),
        surface="context contracts",
        errors=errors,
    )

    client = _read_text(root, "backend/core/engine_client.py")
    _require_tokens(
        client,
        (
            "project_provider_context(context)",
            "context.context_digest",
            "context.source_snapshot",
            "EngineContextHandoff",
            "memory_write_intent",
        ),
        surface="engine context handoff",
        errors=errors,
    )

    execution_boundary = _read_text(
        root,
        "scripts/check_context_execution_boundary.py",
    )
    _require_tokens(
        execution_boundary,
        (
            "ProviderRequest",
            "ProviderRegistry",
            "LlmChat",
            "backend/routes",
            "backend/services",
            "backend/gameforge",
        ),
        surface="context execution boundary",
        errors=errors,
    )

    policy_boundary = _read_text(
        root,
        "scripts/check_instruction_policy_boundary.py",
    )
    _require_tokens(
        policy_boundary,
        (
            "EngineChat",
            "instruction_policy",
            "system_message",
            "backend/routes",
            "backend/services",
            "backend/gameforge",
        ),
        surface="instruction policy boundary",
        errors=errors,
    )

    mirror_receipts: list[dict[str, Any]] = []
    for canonical, mirror in MIRROR_PAIRS:
        canonical_path = root / canonical
        mirror_path = root / mirror
        if not canonical_path.is_file() or not mirror_path.is_file():
            errors.append(f"missing context mirror pair: {canonical} <-> {mirror}")
            continue
        canonical_digest = _sha256(canonical_path)
        mirror_digest = _sha256(mirror_path)
        equal = canonical_digest == mirror_digest
        mirror_receipts.append(
            {
                "canonical": canonical,
                "mirror": mirror,
                "canonical_digest": canonical_digest,
                "mirror_digest": mirror_digest,
                "equal": equal,
            }
        )
        if not equal:
            errors.append(f"context mirror drift: {canonical} != {mirror}")

    construction = _read_json(root, "machine/ai_app_construction.json")
    gap = next(
        (
            item
            for item in construction.get("gap_register", [])
            if isinstance(item, dict)
            and item.get("id") == "gap-context-compiler-convergence"
        ),
        None,
    )
    if not isinstance(gap, dict):
        errors.append("context compiler construction gap is missing")
    else:
        if gap.get("verification_state") != (
            "implementation-complete-pending-dependencies-exact-head-and-independent-closure"
        ):
            errors.append("context compiler verification state is stale")
        progress = gap.get("progress")
        if not isinstance(progress, dict) or progress.get("state") != "implemented_pending_closure":
            errors.append("context compiler progress state is not implemented_pending_closure")

    blueprint = construction.get("context_compiler_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("context compiler blueprint is missing")
    elif blueprint.get("status") != "implemented-pending-closure":
        errors.append("context compiler blueprint status is stale")

    handoff = _read_json(root, "machine/ai_implementation_handoff.json")
    handoff_entry = next(
        (
            item
            for item in handoff.get("entries", [])
            if isinstance(item, dict)
            and item.get("gap") == "gap-context-compiler-convergence"
        ),
        None,
    )
    dependency_graph: list[str] = []
    handoff_digest = None
    if not isinstance(handoff_entry, dict):
        errors.append("context compiler implementation handoff is missing")
    else:
        if handoff_entry.get("implementation_status") != "implemented_pending_closure":
            errors.append("context compiler handoff status is stale")
        dependency_graph = sorted(
            str(item) for item in handoff_entry.get("depends_on", [])
        )
        if set(dependency_graph) != EXPECTED_DEPENDENCIES:
            errors.append("context compiler dependency graph is invalid")
        handoff_digest = hashlib.sha256(
            json.dumps(
                handoff_entry,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    return {
        "schema_version": 1,
        "verifier": VERIFIER_ID,
        "head_sha": (head_sha or "").strip() or None,
        "valid": not errors,
        "errors": errors,
        "boundary_digests": boundary_digests,
        "mirror_pairs": mirror_receipts,
        "dependency_graph": dependency_graph,
        "handoff_digest": handoff_digest,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = verify(
        Path(args.root),
        head_sha=os.getenv("EVIDENCE_HEAD_SHA"),
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.evidence_out:
        path = Path(args.evidence_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    if args.print_evidence:
        print(encoded, end="")
    elif result["valid"]:
        print(
            "independent context compiler verification passed:",
            len(result["boundary_digests"]),
            "boundaries,",
            len(result["mirror_pairs"]),
            "mirror pairs",
        )
    else:
        for error in result["errors"]:
            print("context compiler verification:", error, file=sys.stderr)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
