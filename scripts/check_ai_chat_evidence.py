#!/usr/bin/env python3
"""Structural validator for AI-chat evidence acceptance."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_evidence.json"
SCHEMA = "ai-chat-evidence/v1"
REQUIRED = (
    "CitationIntegrityEngine",
    "EvidenceRequirement",
    "FRESHNESS_REQUIRED",
    "AUTHORITATIVE_SOURCE_REQUIRED",
    "HIGH_ASSURANCE",
    "source-quality-below-policy",
    "freshness-metadata-missing",
    "source-stale",
    "accepted-contradicting-evidence-present",
    "insufficient-independent-evidence",
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
        return ["missing machine/ai_chat_evidence.json"]
    try:
        contract = _json(CONTRACT)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse evidence contract: {exc}"]
    if contract.get("schema_version") != SCHEMA:
        errors.append("evidence schema drifted")
    if contract.get("status") != "implemented_candidate":
        errors.append("evidence status must remain implemented_candidate")

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
        return errors + ["evidence files must be an object"]
    if set(files) != expected:
        errors.append("evidence file roles drifted")
    for role, raw in files.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"invalid evidence file path: {role}")
        elif not (ROOT / raw).is_file():
            errors.append(f"missing evidence file: {role}: {raw}")

    module = ROOT / str(files.get("module", ""))
    if module.is_file():
        try:
            source = module.read_text(encoding="utf-8")
            ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"evidence module is invalid: {exc}")
            source = ""
        if source:
            missing = [token for token in REQUIRED if token not in source]
            if missing:
                errors.append(
                    "evidence gate lost required markers: "
                    + ", ".join(missing)
                )
            forbidden = [token for token in FORBIDDEN if token in source]
            if forbidden:
                errors.append(
                    "evidence gate crossed provider boundary: "
                    + ", ".join(forbidden)
                )

    invariants = contract.get("invariants")
    required_invariants = {
        "citation integrity must pass before a source counts toward support",
        "accepted contradicting evidence blocks release by default",
        "rejected sources never count toward support thresholds",
    }
    if not isinstance(invariants, list):
        errors.append("evidence invariants must be a list")
    elif not required_invariants <= set(map(str, invariants)):
        errors.append("evidence required invariants are incomplete")
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
        "verifier": "ai-chat-evidence-structural-v1",
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
    print("AI chat evidence contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
