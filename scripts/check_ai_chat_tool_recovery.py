#!/usr/bin/env python3
"""Structural validator for AI-chat tool recovery."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_tool_recovery.json"
SCHEMA = "ai-chat-tool-recovery/v1"
FORBIDDEN = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "api.openai.com",
    "api.anthropic.com",
)
REQUIRED = {
    "turn_runtime": (
        "tool_reconciliation_ref",
        "TurnState.TOOL_REQUIRED",
        "ambiguous consequential tool effect must be reconciled",
    ),
    "bridge": (
        "ToolRecoveryAction",
        "durable-tool-reservation-in-doubt",
        "tool-reconciled-no-effect",
        "tool-reconciled-committed",
        "external_effect_started",
    ),
    "receipt_store": (
        "ToolReconciliationOutcome",
        "ToolReconciliationReceipt",
        "resolve_no_effect",
        "resolve_committed",
        "reconciliation evidence was already consumed",
    ),
}


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
        return ["missing machine/ai_chat_tool_recovery.json"]
    try:
        contract = _json(CONTRACT)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse tool recovery contract: {exc}"]

    if contract.get("schema_version") != SCHEMA:
        errors.append("tool recovery schema drifted")
    if contract.get("status") != "implemented_candidate":
        errors.append("tool recovery status must remain implemented_candidate")

    files = contract.get("files")
    if not isinstance(files, dict):
        return errors + ["tool recovery files must be an object"]
    expected = {
        "turn_runtime",
        "bridge",
        "bridge_tests",
        "receipt_store",
        "receipt_store_mirror",
        "receipt_store_tests",
        "validator",
        "independent_verifier",
        "workflow",
        "plan",
    }
    if set(files) != expected:
        errors.append("tool recovery file roles drifted")
    for role, raw in files.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"invalid tool recovery path: {role}")
        elif not (ROOT / raw).is_file():
            errors.append(f"missing tool recovery file: {role}: {raw}")

    for role, markers in REQUIRED.items():
        raw = files.get(role)
        if not isinstance(raw, str):
            continue
        path = ROOT / raw
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"invalid tool recovery source {role}: {exc}")
            continue
        missing = [token for token in markers if token not in source]
        if missing:
            errors.append(
                f"tool recovery markers missing from {role}: "
                + ", ".join(missing)
            )
        forbidden = [token for token in FORBIDDEN if token in source]
        if forbidden:
            errors.append(
                f"tool recovery crossed provider boundary in {role}: "
                + ", ".join(forbidden)
            )

    canonical = ROOT / str(files.get("receipt_store", ""))
    mirror = ROOT / str(files.get("receipt_store_mirror", ""))
    if canonical.is_file() and mirror.is_file():
        if canonical.read_bytes() != mirror.read_bytes():
            errors.append("tool receipt store mirror drifted")

    invariants = contract.get("invariants")
    required_invariants = {
        "in-doubt durable reservations are never blindly replayed",
        "no-effect retry requires explicit durable reconciliation evidence",
        "committed executions cannot be reconciled as no-effect",
    }
    if not isinstance(invariants, list):
        errors.append("tool recovery invariants must be a list")
    elif not required_invariants <= set(map(str, invariants)):
        errors.append("tool recovery required invariants are incomplete")

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
        "verifier": "ai-chat-tool-recovery-structural-v1",
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
    print("AI chat tool recovery contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
