#!/usr/bin/env python3
"""Structural validator for governed AI-chat attachments."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_attachments.json"
SCHEMA = "ai-chat-attachments/v1"
REQUIRED = (
    "_detect_format",
    "claimed MIME does not match attachment bytes",
    "filename extension does not match attachment bytes",
    "attachment-sha256:",
    "quarantined attachment cannot enter context",
    "ContextTrust.UNTRUSTED_EVIDENCE",
    "admit_multimodal_reference",
    "multimodal payload does not match attachment digest",
)
FORBIDDEN = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "api.openai.com",
    "api.anthropic.com",
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
        return ["missing machine/ai_chat_attachments.json"]
    try:
        contract = _json(CONTRACT)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse attachment contract: {exc}"]
    if contract.get("schema_version") != SCHEMA:
        errors.append("attachment schema drifted")
    if contract.get("status") != "implemented_candidate":
        errors.append("attachment status must remain implemented_candidate")

    files = contract.get("files")
    expected = {
        "module",
        "tests",
        "validator",
        "independent_verifier",
        "workflow",
        "plan",
    }
    if not isinstance(files, dict):
        return errors + ["attachment files must be an object"]
    if set(files) != expected:
        errors.append("attachment file roles drifted")
    for role, raw in files.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"invalid attachment file path: {role}")
        elif not (ROOT / raw).is_file():
            errors.append(f"missing attachment file: {role}: {raw}")

    module = ROOT / str(files.get("module", ""))
    if module.is_file():
        try:
            source = module.read_text(encoding="utf-8")
            ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"attachment module is invalid: {exc}")
            source = ""
        if source:
            missing = [token for token in REQUIRED if token not in source]
            if missing:
                errors.append(
                    "attachment admission lost fail-closed markers: "
                    + ", ".join(missing)
                )
            forbidden = [token for token in FORBIDDEN if token in source]
            if forbidden:
                errors.append(
                    "attachment admission crossed provider boundary: "
                    + ", ".join(forbidden)
                )

    invariants = contract.get("invariants")
    required_invariants = {
        "byte signatures rather than filename or claimed MIME determine supported format",
        "quarantined attachments cannot enter context",
        "attachment extracted text is always projected as untrusted evidence",
    }
    if not isinstance(invariants, list):
        errors.append("attachment invariants must be a list")
    elif not required_invariants <= set(map(str, invariants)):
        errors.append("attachment required invariants are incomplete")
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
        "verifier": "ai-chat-attachments-structural-v1",
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
    print("AI chat attachment contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
