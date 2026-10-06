#!/usr/bin/env python3
"""Fail-closed structural validator for AI-chat model routing v2."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_model_routing.json"
SCHEMA = "ai-chat-model-routing/v1"
FORBIDDEN = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "api.openai.com",
    "api.anthropic.com",
    "from openai import",
    "import openai",
    "from anthropic import",
    "import anthropic",
)
REQUIRED = (
    "class RouteRequest",
    "from_turn_budget",
    "allowed_jurisdictions",
    "require_provider_receipt",
    "minimum_observations",
    "max_telemetry_age_s",
    "class EndpointQuarantine",
    "quarantined:",
    "provider receipt capability required",
    "telemetry missing",
    "def constraint_dict",
    "def digest",
)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> list[str]:
    errors: list[str] = []
    if not CONTRACT.is_file():
        return ["missing machine/ai_chat_model_routing.json"]
    try:
        contract = _json(CONTRACT)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse model routing contract: {exc}"]

    if contract.get("schema_version") != SCHEMA:
        errors.append("model routing schema drifted")
    if contract.get("status") != "implemented_candidate":
        errors.append("model routing status must remain implemented_candidate")

    files = contract.get("files")
    if not isinstance(files, dict):
        return errors + ["model routing files must be an object"]
    expected = {
        "canonical",
        "mirror",
        "tests",
        "validator",
        "independent_verifier",
        "workflow",
        "plan",
    }
    if set(files) != expected:
        errors.append("model routing file roles drifted")
    for role, raw in files.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"invalid model routing path: {role}")
        elif not (ROOT / raw).is_file():
            errors.append(f"missing model routing file: {role}: {raw}")

    canonical = ROOT / str(files.get("canonical", ""))
    mirror = ROOT / str(files.get("mirror", ""))
    if canonical.is_file() and mirror.is_file():
        if canonical.read_bytes() != mirror.read_bytes():
            errors.append("model routing compatibility mirror drifted")
        try:
            source = canonical.read_text(encoding="utf-8")
            ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"canonical model router is invalid: {exc}")
            source = ""
        if source:
            missing = [token for token in REQUIRED if token not in source]
            if missing:
                errors.append(
                    "model router lost hard-constraint markers: "
                    + ", ".join(missing)
                )
            forbidden = [token for token in FORBIDDEN if token in source]
            if forbidden:
                errors.append(
                    "model router crossed provider boundary: "
                    + ", ".join(forbidden)
                )

    required_invariants = {
        "turn execution budgets own routing latency cost and output ceilings",
        "privacy is a hard eligibility constraint for primary and fallback endpoints",
        "quarantined endpoints are ineligible until explicit clear or expiry",
        "every fallback candidate satisfies the same immutable route request",
    }
    invariants = contract.get("invariants")
    if not isinstance(invariants, list):
        errors.append("model routing invariants must be a list")
    elif not required_invariants <= set(map(str, invariants)):
        errors.append("model routing required invariants are incomplete")

    hard = contract.get("hard_constraint_fields")
    if not isinstance(hard, list):
        errors.append("hard_constraint_fields must be a list")
    else:
        needed = {
            "privacy",
            "latency_budget_ms",
            "cost_budget",
            "minimum_observations",
            "max_telemetry_age_s",
            "allowed_jurisdictions",
            "require_provider_receipt",
        }
        if not needed <= set(map(str, hard)):
            errors.append("model routing hard constraints are incomplete")

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
    payload: dict[str, object] = {
        "schema_version": SCHEMA,
        "verifier": "ai-chat-model-routing-structural-v1",
        "head_sha": head_sha.strip(),
        "valid": not errors,
        "errors": errors,
        "contract_digest": _sha(CONTRACT),
        "digests": digests,
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
    print("AI chat model routing contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
