#!/usr/bin/env python3
"""Independent fail-closed verifier for hostile gap G015 compensation authority."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("machine/non_idempotent_compensation_contract.json")
EXPECTED_SCHEMA = "skeleton.ai.non_idempotent_compensation_contract.v1"


class CompensationContractError(RuntimeError):
    pass


def _load() -> dict[str, Any]:
    try:
        value = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompensationContractError(f"cannot read {CONTRACT}") from exc
    if not isinstance(value, dict):
        raise CompensationContractError("compensation contract must be an object")
    return value


def _text_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CompensationContractError(f"{field} must be a non-empty list")
    if any(not isinstance(item, str) or not item for item in value):
        raise CompensationContractError(f"{field} must contain non-empty text")
    if value != sorted(set(value)):
        raise CompensationContractError(f"{field} must be sorted and duplicate-free")
    return value


def validate() -> dict[str, Any]:
    contract = _load()
    errors: list[str] = []

    if contract.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("G015 contract schema drift")
    if contract.get("status") != "active":
        errors.append("G015 contract must be active")
    if contract.get("gap_id") != "G015":
        errors.append("G015 gap identity drift")
    if contract.get("completion_authority") is not False:
        errors.append("G015 implementation contract cannot self-grant completion authority")

    required_paths = {
        "canonical_runtime": contract.get("canonical_runtime"),
        "ai_mirror": contract.get("ai_mirror"),
        "tool_contract": contract.get("tool_contract"),
        "durable_transaction_substrate": contract.get("durable_transaction_substrate"),
        "exact_head_workflow": contract.get("exact_head_workflow"),
    }
    for field, raw in required_paths.items():
        if not isinstance(raw, str) or not raw:
            errors.append(f"{field} must be a repository path")
            continue
        if not (ROOT / raw).is_file():
            errors.append(f"{field} missing: {raw}")

    try:
        runtime_types = _text_list(
            contract.get("required_runtime_types"),
            "required_runtime_types",
        )
        source_markers = _text_list(
            contract.get("source_markers"),
            "source_markers",
        )
        acceptance_tests = _text_list(
            contract.get("acceptance_tests"),
            "acceptance_tests",
        )
        guards = contract.get("required_guards")
        if not isinstance(guards, list) or len(guards) < 8 or any(
            not isinstance(item, str) or not item.strip() for item in guards
        ):
            raise CompensationContractError(
                "required_guards must contain at least eight text invariants"
            )
    except CompensationContractError as exc:
        errors.append(str(exc))
        runtime_types = []
        source_markers = []
        acceptance_tests = []

    for path in acceptance_tests:
        if not (ROOT / path).is_file():
            errors.append(f"acceptance test missing: {path}")

    canonical = required_paths.get("canonical_runtime")
    mirror = required_paths.get("ai_mirror")
    source = ""
    if isinstance(canonical, str) and (ROOT / canonical).is_file():
        source = (ROOT / canonical).read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            errors.append(f"canonical tool saga is not valid Python: {exc}")
            tree = None
        if tree is not None:
            declared_types = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for required in runtime_types:
                if required not in declared_types:
                    errors.append(f"canonical tool saga missing runtime type {required}")
        for marker in source_markers:
            if marker not in source:
                errors.append(f"canonical tool saga missing G015 guard marker: {marker}")

    if (
        isinstance(canonical, str)
        and isinstance(mirror, str)
        and (ROOT / canonical).is_file()
        and (ROOT / mirror).is_file()
        and (ROOT / canonical).read_bytes() != (ROOT / mirror).read_bytes()
    ):
        errors.append("canonical tool saga and governed AI mirror diverge")

    transaction_path = required_paths.get("durable_transaction_substrate")
    if isinstance(transaction_path, str) and (ROOT / transaction_path).is_file():
        transaction_source = (ROOT / transaction_path).read_text(encoding="utf-8")
        for marker in (
            "DurableSagaStateStore",
            "prepare_step",
            "mark_effect_applied",
            "begin_compensation",
            "pending_compensations",
        ):
            if marker not in transaction_source:
                errors.append(
                    f"durable transaction substrate missing compensation marker: {marker}"
                )

    return {
        "schema_version": "skeleton.ai.non_idempotent_compensation_receipt.v1",
        "valid": not errors,
        "status": "valid" if not errors else "rejected",
        "gap_id": "G015",
        "runtime_type_count": len(runtime_types),
        "acceptance_test_count": len(acceptance_tests),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate()
    except CompensationContractError as exc:
        print(f"G015 compensation contract: rejected: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["valid"]:
        print(
            "G015 compensation contract: OK "
            f"({result['runtime_type_count']} runtime types; "
            f"{result['acceptance_test_count']} executable suites)"
        )
    else:
        for error in result["errors"]:
            print(f"  - {error}", file=sys.stderr)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
