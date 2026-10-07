#!/usr/bin/env python3
"""Independent rehasher for AI-chat runtime exact-head evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_runtime_contract.json"
EXPECTED_SCHEMA = "ai-chat-runtime/v1"
EXPECTED_VERIFIER = "ai-chat-runtime-structural-v1"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_without_field(payload: dict[str, object], field: str) -> str:
    copy = dict(payload)
    copy.pop(field, None)
    return hashlib.sha256(
        json.dumps(
            copy,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def verify(receipt_path: Path, expected_head: str) -> dict[str, object]:
    errors: list[str] = []
    receipt = _json(receipt_path)
    contract = _json(CONTRACT)

    if receipt.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("receipt schema_version drifted")
    if receipt.get("verifier") != EXPECTED_VERIFIER:
        errors.append("unexpected structural verifier identity")
    if receipt.get("head_sha") != expected_head:
        errors.append("structural receipt is not exact-head")
    if receipt.get("valid") is not True:
        errors.append("structural verifier did not report valid")
    if receipt.get("errors"):
        errors.append("structural verifier receipt contains errors")
    if contract.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("contract schema_version drifted")

    claimed_contract = receipt.get("contract_digest")
    actual_contract = _sha256(CONTRACT)
    if claimed_contract != actual_contract:
        errors.append("contract digest mismatch")

    files = contract.get("files")
    if not isinstance(files, dict):
        errors.append("contract files map is invalid")
        files = {}
    claimed = receipt.get("digests")
    if not isinstance(claimed, dict):
        errors.append("receipt digests map is invalid")
        claimed = {}

    actual: dict[str, str] = {}
    for role, raw in sorted(files.items()):
        if not isinstance(raw, str) or not raw:
            errors.append(f"invalid contract file path for {role}")
            continue
        path = ROOT / raw
        if not path.is_file():
            errors.append(f"contract file missing during independent verify: {role}")
            continue
        actual[str(role)] = _sha256(path)
    if actual != claimed:
        errors.append("independent file digest map mismatch")

    claimed_receipt_digest = receipt.get("evidence_digest")
    recomputed_receipt_digest = _digest_without_field(receipt, "evidence_digest")
    if claimed_receipt_digest != recomputed_receipt_digest:
        errors.append("structural receipt digest mismatch")

    result: dict[str, object] = {
        "schema_version": EXPECTED_SCHEMA,
        "verifier": "independent-ai-chat-runtime-rehasher-v1",
        "expected_head": expected_head,
        "valid": not errors,
        "errors": errors,
        "contract_digest": actual_contract,
        "receipt_digest": _sha256(receipt_path),
        "structural_evidence_digest": claimed_receipt_digest,
        "recomputed_structural_evidence_digest": recomputed_receipt_digest,
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
    if not result["valid"]:
        for error in result["errors"]:
            print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
