#!/usr/bin/env python3
"""Fail-closed structural verifier for the October 2026 chat resilience pass."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_resilience_v2_contract.json"


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def parse_module(path: Path) -> ast.Module:
    require(path.is_file(), f"missing required surface: {path.relative_to(ROOT)}")
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise VerificationError(f"syntax error in {path.relative_to(ROOT)}: {exc}") from exc


def names(tree: ast.Module, node_type: type[ast.AST]) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, node_type) and isinstance(getattr(node, "name", None), str):
            result.add(node.name)
    return result


def imported_roots(tree: ast.Module) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".", 1)[0])
    return result


def verify() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(payload["schema_version"] == 1, "unexpected contract schema")
    require(payload["effective_date"] == "2026-10-06", "unexpected standard date")
    require(payload["production_authority"] is False, "decision plane cannot gain production authority")
    require(
        payload["promotion"]["status"] == "implemented_candidate",
        "pass must remain implemented_candidate before exact-head qualification",
    )
    require(
        payload["promotion"]["completion_checkbox"] is False,
        "contract cannot self-attest completion",
    )
    require(
        payload["promotion"]["verification_signature"] is None,
        "contract cannot fabricate verification signature",
    )

    surfaces = payload["surfaces"]
    placement_path = ROOT / surfaces["model_placement"]
    recovery_path = ROOT / surfaces["tool_recovery"]
    tests_path = ROOT / surfaces["regressions"]
    masterplan_path = ROOT / surfaces["masterplan"]
    workflow_path = ROOT / surfaces["workflow"]

    placement = parse_module(placement_path)
    recovery = parse_module(recovery_path)
    parse_module(tests_path)

    placement_classes = names(placement, ast.ClassDef)
    placement_functions = names(placement, ast.FunctionDef)
    recovery_classes = names(recovery, ast.ClassDef)
    recovery_functions = names(recovery, ast.FunctionDef)

    require(
        {
            "EndpointProfile",
            "EndpointHealth",
            "PlacementBudget",
            "PlacementRequest",
            "PlacementPolicy",
            "PlacementDecision",
            "FailoverDecision",
            "ModelPlacementEngine",
        }.issubset(placement_classes),
        "placement surface is structurally incomplete",
    )
    require(
        {"plan", "authorize_failover"}.issubset(placement_functions),
        "placement engine lacks plan/failover boundaries",
    )
    require(
        {
            "ToolRecoveryEvidence",
            "ToolRecoveryDecision",
            "PriorToolOutcome",
            "ToolRecoveryAction",
        }.issubset(recovery_classes),
        "tool recovery surface is structurally incomplete",
    )
    require(
        "decide_tool_recovery" in recovery_functions,
        "tool recovery decision function missing",
    )

    forbidden_provider_sdk_roots = {
        "openai",
        "anthropic",
        "google",
        "boto3",
        "requests",
        "httpx",
        "urllib",
        "socket",
    }
    placement_imports = imported_roots(placement)
    require(
        not (placement_imports & forbidden_provider_sdk_roots),
        "placement decision plane imported provider/network execution dependencies",
    )

    placement_text = placement_path.read_text(encoding="utf-8")
    recovery_text = recovery_path.read_text(encoding="utf-8")
    masterplan_text = masterplan_path.read_text(encoding="utf-8")
    workflow_text = workflow_path.read_text(encoding="utf-8")

    for token in (
        "privacy-ceiling-insufficient",
        "health-stale",
        "circuit-breaker-open",
        "failover-budget-amplified",
        "fallback-not-admitted-by-prior-receipt",
        'production_authority: bool = False',
    ):
        require(token in placement_text, f"placement invariant token missing: {token}")

    for token in (
        "consequential-outcome-unknown",
        "write-retry-requires-durable-failure-receipt",
        "write-retry-requires-idempotency-key",
        "security-sensitive-retry-requires-fresh-user-authority",
        "receipt-arguments-binding-mismatch",
        'production_authority: bool = False',
    ):
        require(token in recovery_text, f"tool recovery invariant token missing: {token}")

    require(
        "### Volume 5 — routing v2" in masterplan_text
        and "Status: **implemented candidate; provider-runtime cutover and exact-head qualification pending**."
        in masterplan_text,
        "masterplan Volume 5 status not synchronized",
    )
    require(
        "### Volume 6 — tool recovery integration" in masterplan_text
        and "Status: **implemented candidate; turn-runtime cutover and exact-head qualification pending**."
        in masterplan_text,
        "masterplan Volume 6 status not synchronized",
    )

    for token in (
        "persist-credentials: false",
        "python -m compileall -q",
        "verify_ai_chat_resilience_v2.py --json",
        "test_ai_chat_resilience_v2.py",
    ):
        require(token in workflow_text, f"exact-head workflow token missing: {token}")

    return {
        "ok": True,
        "standard_id": payload["standard_id"],
        "effective_date": payload["effective_date"],
        "placement_invariants": len(payload["placement_invariants"]),
        "tool_recovery_invariants": len(payload["tool_recovery_invariants"]),
        "promotion_status": payload["promotion"]["status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = verify()
    except (OSError, KeyError, TypeError, ValueError, VerificationError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "AI chat resilience v2 structural verification passed: "
            f"{result['placement_invariants']} placement + "
            f"{result['tool_recovery_invariants']} tool-recovery invariants"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
