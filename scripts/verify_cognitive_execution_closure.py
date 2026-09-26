#!/usr/bin/env python3
"""Independent cognitive-execution closure verifier.

This verifier intentionally does not import the cognitive runtime, execution
repository, engine service, provider runtime, or tool runtime. It reconstructs
the expected orchestration boundary directly from source text and the machine
contracts, then checks canonical ownership, AI-tree mirror parity, dependency
declarations, exact-head status binding, and provider-SDK isolation.
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
    "skeleton/contracts/ai_execution.py": (
        "AIExecutionRequest",
        "AIExecutionResult",
        "AgentTurn",
        "ExecutionCheckpoint",
        "ExecutionFinalizationIntent",
        "ExecutionState",
        "identity_digest",
    ),
    "skeleton/intelligence/execution_runtime.py": (
        "class CognitiveExecutionRuntime",
        "async def start(",
        "async def resume(",
        "_run_provider_turn",
        "_execute_pending_tools",
        "_verify_and_finalize",
        "_commit_terminal_result",
        "ExecutionState.WAITING_FOR_USER",
        "approval_refs",
        "storage_meter",
    ),
    "skeleton/persistence/execution_repository.py": (
        "class SQLiteExecutionRepository",
        "def checkpoint(",
        "def append_turn(",
        "def stage_finalization(",
        "def finalize_staged(",
        "def recoverable(",
        "ai_execution_outbox",
        "BEGIN IMMEDIATE",
    ),
    "skeleton/api/engine_service.py": (
        "ensure_execution_admission",
        "complete_execution_admission",
        "meter_execution_storage",
        "pending_tool_approvals",
        "approve_tool_call",
    ),
    "skeleton/api/engine_runtime.py": (
        "CognitiveExecutionRuntime(",
        "storage_meter=",
        "ensure_execution_admission",
        "complete_execution_admission",
    ),
}

MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "skeleton/contracts/ai_execution.py",
        "skeleton/ai/runtime/contracts/ai_execution.py",
    ),
    (
        "skeleton/intelligence/execution_runtime.py",
        "skeleton/ai/runtime/intelligence/execution_runtime.py",
    ),
    (
        "skeleton/persistence/execution_repository.py",
        "skeleton/ai/runtime/persistence/execution_repository.py",
    ),
    (
        "skeleton/api/engine_service.py",
        "skeleton/ai/runtime/api/engine_service.py",
    ),
    (
        "skeleton/api/engine_runtime.py",
        "skeleton/ai/runtime/api/engine_runtime.py",
    ),
)

EXPECTED_DEPENDENCIES = {
    "gap-state-authority-convergence",
    "gap-governance-registry",
    "gap-cost-admission",
    "gap-conversation-state-authority",
    "gap-memory-durable-authority",
    "gap-tool-runtime-convergence",
    "gap-context-compiler-convergence",
    "gap-provider-interaction-protocol",
    "gap-verification-evidence-contract",
}

FORBIDDEN_PROVIDER_TOKENS = (
    "import openai",
    "from openai",
    "AsyncOpenAI(",
    "OpenAI(",
    "api.openai.com",
    "OPENAI_API_KEY",
)


class VerificationError(RuntimeError):
    """Independent cognitive-execution verification failed."""


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
            errors.append(f"cognitive execution boundary is missing: {rel}")
            continue
        source = _read_text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost cognitive execution token: {token}")
        if rel in {
            "skeleton/contracts/ai_execution.py",
            "skeleton/intelligence/execution_runtime.py",
            "skeleton/persistence/execution_repository.py",
            "skeleton/api/engine_service.py",
            "skeleton/api/engine_runtime.py",
        }:
            for token in FORBIDDEN_PROVIDER_TOKENS:
                if token in source:
                    errors.append(
                        f"{rel} regained direct provider ownership: {token}"
                    )
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


def _find_entry(
    payload: dict[str, Any],
    key: str,
    value: str,
) -> dict[str, Any] | None:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return None
    for item in entries:
        if isinstance(item, dict) and item.get(key) == value:
            return item
    return None


def _verify_machine_contracts(root: Path, errors: list[str]) -> dict[str, Any]:
    handoff = _load_json(root / "machine/ai_implementation_handoff.json")
    entry = _find_entry(
        handoff,
        "gap",
        "gap-cognitive-execution-loop",
    )
    if entry is None:
        errors.append("cognitive execution handoff entry is missing")
        return {}

    dependencies = entry.get("depends_on")
    if not isinstance(dependencies, list):
        errors.append("cognitive execution depends_on must be a list")
        dependencies = []
    actual_dependencies = {str(item) for item in dependencies}
    if actual_dependencies != EXPECTED_DEPENDENCIES:
        errors.append(
            "cognitive execution dependency graph mismatch: "
            + ", ".join(sorted(actual_dependencies))
        )

    closure_gate = str(entry.get("closure_gate") or "")
    for phrase in (
        "deterministically retrieve",
        "governed tools",
        "wait/resume",
        "verify",
        "persist",
        "stream",
    ):
        if phrase not in closure_gate:
            errors.append(
                "cognitive execution closure gate lost invariant phrase: "
                + phrase
            )

    implementation_status = str(entry.get("implementation_status") or "")
    if implementation_status not in {
        "implementation-complete",
        "closed",
    }:
        errors.append(
            "cognitive execution handoff is not implementation-complete"
        )

    construction = _load_json(root / "machine/ai_app_construction.json")
    gaps = construction.get("gap_register")
    dependency_status: dict[str, str] = {}
    cognitive_status = "missing"
    if not isinstance(gaps, list):
        errors.append("construction gap_register must be a list")
    else:
        for item in gaps:
            if not isinstance(item, dict):
                continue
            gap_id = str(item.get("id") or "")
            status = str(item.get("status") or "")
            if gap_id == "gap-cognitive-execution-loop":
                cognitive_status = status
            if gap_id in EXPECTED_DEPENDENCIES:
                dependency_status[gap_id] = status

    missing = sorted(EXPECTED_DEPENDENCIES - set(dependency_status))
    if missing:
        errors.append(
            "cognitive execution dependency statuses missing: "
            + ", ".join(missing)
        )

    blueprint = construction.get("cognitive_runtime_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("cognitive_runtime_blueprint is missing")
    else:
        if blueprint.get("gap") != "gap-cognitive-execution-loop":
            errors.append("cognitive runtime blueprint gap binding is invalid")
        if blueprint.get("status") not in {
            "implemented-pending-closure",
            "closed",
        }:
            errors.append(
                "cognitive runtime blueprint is not implemented-pending-closure"
            )
        target_modules = blueprint.get("target_modules")
        if not isinstance(target_modules, dict):
            errors.append("cognitive runtime target_modules must be an object")
        else:
            expected_paths = {
                "contracts": "skeleton/contracts/ai_execution.py",
                "runtime": "skeleton/intelligence/execution_runtime.py",
                "repository": "skeleton/persistence/execution_repository.py",
                "provider_boundary": "skeleton/provider_runtime.py",
            }
            for key, expected_path in expected_paths.items():
                node = target_modules.get(key)
                if not isinstance(node, dict) or node.get("path") != expected_path:
                    errors.append(
                        f"cognitive runtime target module mismatch: {key}"
                    )

    if cognitive_status == "closed":
        open_dependencies = sorted(
            gap_id
            for gap_id in EXPECTED_DEPENDENCIES
            if dependency_status.get(gap_id) != "closed"
        )
        if open_dependencies:
            errors.append(
                "closed cognitive execution gap has non-closed dependencies: "
                + ", ".join(open_dependencies)
            )
    elif cognitive_status != "open":
        errors.append("cognitive execution construction status is invalid")

    entry["_verified_dependency_status"] = {
        gap_id: dependency_status.get(gap_id, "missing")
        for gap_id in sorted(EXPECTED_DEPENDENCIES)
    }
    entry["_verified_cognitive_status"] = cognitive_status
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
        "verifier": "independent-cognitive-execution-v1",
        "head_sha": os.environ.get("GITHUB_SHA", "").strip() or "unknown",
        "boundary_digests": boundary_digests,
        "mirror_pairs": mirrors,
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "dependency_status": dict(
            handoff.get("_verified_dependency_status") or {}
        ),
        "cognitive_status": handoff.get("_verified_cognitive_status"),
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
        print(f"independent-cognitive-execution: rejected: {exc}", file=sys.stderr)
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
        print("independent-cognitive-execution: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "independent-cognitive-execution: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
