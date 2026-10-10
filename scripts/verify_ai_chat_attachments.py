#!/usr/bin/env python3
"""Independent exact-head rehasher for AI-chat attachment admission."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_attachments.json"
SCHEMA = "ai-chat-attachments/v1"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rehash(payload: dict[str, object]) -> str:
    value = dict(payload)
    value.pop("evidence_digest", None)
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def verify(receipt_path: Path, expected_head: str) -> dict[str, object]:
    receipt = _json(receipt_path)
    contract = _json(CONTRACT)
    errors: list[str] = []
    if receipt.get("schema_version") != SCHEMA:
        errors.append("attachment receipt schema drifted")
    if receipt.get("verifier") != "ai-chat-attachments-structural-v1":
        errors.append("unexpected attachment structural verifier")
    if receipt.get("head_sha") != expected_head:
        errors.append("attachment receipt is not exact-head")
    if receipt.get("valid") is not True or receipt.get("errors"):
        errors.append("attachment structural verifier did not pass")
    if receipt.get("contract_digest") != _sha(CONTRACT):
        errors.append("attachment contract digest mismatch")

    files = contract.get("files")
    if not isinstance(files, dict):
        errors.append("attachment files contract invalid")
        files = {}
    actual = {
        str(role): _sha(ROOT / str(path))
        for role, path in sorted(files.items())
        if isinstance(path, str) and (ROOT / path).is_file()
    }
    if actual != receipt.get("digests"):
        errors.append("attachment file digest map mismatch")
    recomputed = _rehash(receipt)
    if receipt.get("evidence_digest") != recomputed:
        errors.append("attachment evidence digest mismatch")

    result: dict[str, object] = {
        "schema_version": SCHEMA,
        "verifier": "independent-ai-chat-attachments-v1",
        "expected_head": expected_head,
        "valid": not errors,
        "errors": errors,
        "contract_digest": _sha(CONTRACT),
        "receipt_digest": _sha(receipt_path),
        "structural_evidence_digest": receipt.get("evidence_digest"),
        "recomputed_structural_evidence_digest": recomputed,
        "file_digests": actual,
    }
    result["verifier_digest"] = hashlib.sha256(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt")
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args()
    result = verify(Path(args.receipt), args.head_sha.strip())
    if args.evidence_out:
        Path(args.evidence_out).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
