#!/usr/bin/env python3
"""Fail-closed structural validator for AI-chat cross-plane resilience."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_cross_plane_resilience.json"
SCHEMA = "ai-chat-cross-plane-resilience/v1"
DEPENDENT_CONTRACTS = (
    ("machine/ai_chat_runtime_contract.json", "implemented_candidate"),
    ("machine/ai_chat_model_routing.json", "implemented_candidate"),
    ("machine/ai_chat_tool_recovery.json", "implemented_candidate"),
    ("machine/ai_chat_attachments.json", "implemented_candidate"),
)
FORBIDDEN_BINDING_IMPORTS = {
    "openai",
    "anthropic",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "boto3",
}


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _imports(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _defined(tree: ast.Module, node_type: type[ast.AST]) -> set[str]:
    return {
        str(node.name)
        for node in ast.walk(tree)
        if isinstance(node, node_type) and isinstance(getattr(node, "name", None), str)
    }


def validate() -> list[str]:
    errors: list[str] = []
    if not CONTRACT.is_file():
        return ["missing machine/ai_chat_cross_plane_resilience.json"]
    try:
        contract = _json(CONTRACT)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse cross-plane resilience contract: {exc}"]

    if contract.get("schema_version") != SCHEMA:
        errors.append("cross-plane resilience schema drifted")
    if contract.get("status") != "implemented_candidate":
        errors.append("cross-plane resilience must remain implemented_candidate")

    authority = contract.get("authority")
    if not isinstance(authority, dict) or authority.get("execution") is not False:
        errors.append("cross-plane resilience cannot gain execution authority")

    promotion = contract.get("promotion")
    if not isinstance(promotion, dict):
        errors.append("cross-plane promotion contract missing")
    else:
        if promotion.get("completion_checkbox") is not False:
            errors.append("cross-plane contract cannot self-attest completion")
        if promotion.get("verification_signature") is not None:
            errors.append("cross-plane contract cannot fabricate verification signature")

    files = contract.get("files")
    expected_roles = {
        "binding",
        "assistant_exports",
        "canonical_router",
        "router_mirror",
        "tests",
        "routing_contract",
        "validator",
        "independent_verifier",
        "workflow",
        "plan",
    }
    if not isinstance(files, dict):
        return errors + ["cross-plane files must be an object"]
    if set(files) != expected_roles:
        errors.append("cross-plane file roles drifted")
    resolved: dict[str, Path] = {}
    for role, raw in files.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"invalid cross-plane file path: {role}")
            continue
        path = ROOT / raw
        resolved[str(role)] = path
        if not path.is_file():
            errors.append(f"missing cross-plane file: {role}: {raw}")

    canonical = resolved.get("canonical_router")
    mirror = resolved.get("router_mirror")
    if canonical and mirror and canonical.is_file() and mirror.is_file():
        if canonical.read_bytes() != mirror.read_bytes():
            errors.append("canonical and AI compatibility model routers drifted")
        router_source = canonical.read_text(encoding="utf-8")
        for token in (
            "def from_turn_snapshot(",
            "BudgetGovernor.assess(snapshot.budget, snapshot.usage)",
            "model-call budget exhausted",
            "context exceeds remaining input-token budget",
            "expected output exceeds remaining output-token budget",
        ):
            if token not in router_source:
                errors.append(f"router lost remaining-authority marker: {token}")

    binding = resolved.get("binding")
    if binding and binding.is_file():
        try:
            binding_source = binding.read_text(encoding="utf-8")
            tree = ast.parse(binding_source, filename=str(binding))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"cross-plane binding is invalid Python: {exc}")
        else:
            classes = _defined(tree, ast.ClassDef)
            functions = _defined(tree, ast.FunctionDef)
            required_classes = {
                "TurnAuthorityFingerprint",
                "TurnRouteBinding",
                "TurnToolRecoveryBinding",
                "TurnAttachmentBinding",
                "CrossPlaneResilienceReceipt",
            }
            required_functions = {
                "remaining_execution_budget",
                "route_request_for_remaining_turn",
                "bind_route_decision",
                "bind_tool_recovery_decision",
                "bind_attachment_batch",
                "build_cross_plane_resilience_receipt",
            }
            if not required_classes <= classes:
                errors.append("cross-plane binding classes are incomplete")
            if not required_functions <= functions:
                errors.append("cross-plane binding functions are incomplete")
            forbidden = _imports(tree) & FORBIDDEN_BINDING_IMPORTS
            if forbidden:
                errors.append(
                    "cross-plane evidence layer imported execution/network dependencies: "
                    + ", ".join(sorted(forbidden))
                )
            for token in (
                "snapshot.has_ambiguous_external_effect",
                "provider_receipt_required",
                "production_authority: bool = False",
                "RouteRequest.from_turn_snapshot",
            ):
                if token not in binding_source:
                    errors.append(f"cross-plane binding lost invariant marker: {token}")

    tests = resolved.get("tests")
    if tests and tests.is_file():
        try:
            test_tree = ast.parse(tests.read_text(encoding="utf-8"), filename=str(tests))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"cross-plane tests are invalid Python: {exc}")
        else:
            test_count = sum(
                1
                for node in ast.walk(test_tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and str(node.name).startswith("test_")
            )
            if test_count < 20:
                errors.append(
                    f"cross-plane adversarial suite too small: {test_count} < 20"
                )

    required_invariants = {
        "retry and failover routing project only remaining durable turn authority",
        "provider-receipt requirements survive routing and must be satisfied before post-model qualification",
        "unresolved consequential external effects block cross-plane qualification",
        "quarantined attachments cannot be bound into turn context evidence",
        "canonical and AI compatibility model routers remain byte-identical",
    }
    invariants = contract.get("invariants")
    if not isinstance(invariants, list):
        errors.append("cross-plane invariants must be a list")
    elif not required_invariants <= set(map(str, invariants)):
        errors.append("cross-plane required invariants are incomplete")

    for relative, expected_status in DEPENDENT_CONTRACTS:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing dependent contract: {relative}")
            continue
        try:
            dependent = _json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"cannot parse dependent contract {relative}: {exc}")
            continue
        if dependent.get("status") != expected_status:
            errors.append(
                f"dependent contract {relative} is not {expected_status}"
            )

    plan = resolved.get("plan")
    if plan and plan.is_file():
        text = plan.read_text(encoding="utf-8")
        if "### Cross-volume resilience binding" not in text:
            errors.append("masterplan missing cross-volume resilience binding")
        if (
            "Status: **implemented candidate; exact-head qualification pending**."
            not in text
        ):
            errors.append("masterplan cross-volume status is not fail-closed candidate")

    workflow = resolved.get("workflow")
    if workflow and workflow.is_file():
        text = workflow.read_text(encoding="utf-8")
        for token in (
            "persist-credentials: false",
            "github.event.pull_request.head.sha || github.sha",
            "check_ai_chat_cross_plane_resilience.py",
            "verify_ai_chat_cross_plane_resilience.py",
            "test_ai_chat_cross_plane_resilience.py",
            "check_ai_chat_model_routing.py",
            "check_ai_file_tree.py",
        ):
            if token not in text:
                errors.append(f"cross-plane workflow missing exact-head control: {token}")

    return errors


def evidence(head_sha: str) -> dict[str, object]:
    errors = validate()
    contract = _json(CONTRACT)
    files = contract.get("files") or {}
    digests = {
        str(role): _sha(ROOT / str(path))
        for role, path in sorted(files.items())
        if isinstance(path, str) and (ROOT / path).is_file()
    }
    dependent_digests = {
        relative: _sha(ROOT / relative)
        for relative, _ in DEPENDENT_CONTRACTS
        if (ROOT / relative).is_file()
    }
    payload: dict[str, object] = {
        "schema_version": SCHEMA,
        "verifier": "ai-chat-cross-plane-resilience-structural-v1",
        "head_sha": head_sha.strip(),
        "valid": not errors,
        "errors": errors,
        "contract_digest": _sha(CONTRACT),
        "digests": digests,
        "dependent_contract_digests": dependent_digests,
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args()

    if args.head_sha:
        result = evidence(args.head_sha)
        if args.evidence_out:
            Path(args.evidence_out).write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_evidence:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1

    errors = validate()
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("AI chat cross-plane resilience contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
