#!/usr/bin/env python3
"""Independent exact-head rehasher for enterprise system architecture evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "machine" / "enterprise_system_architecture.json"
EXPECTED_SCHEMA = "enterprise-system-architecture/v1"
EXPECTED_VERIFIER = "enterprise-system-architecture-structural-v1"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_without(payload: dict[str, Any], field: str) -> str:
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


def verify(
    receipt_path: Path,
    expected_head: str,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    receipt = _load(receipt_path)
    contract = _load(repo_root / "machine" / "enterprise_system_architecture.json")

    if receipt.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("receipt schema_version drifted")
    if receipt.get("verifier") != EXPECTED_VERIFIER:
        errors.append("unexpected structural verifier identity")
    if receipt.get("head_sha") != expected_head:
        errors.append("enterprise structural receipt is not exact-head")
    if receipt.get("valid") is not True:
        errors.append("enterprise structural verifier did not report valid")
    if receipt.get("errors"):
        errors.append("enterprise structural receipt contains errors")
    if receipt.get("plan_complete") is not True:
        errors.append("enterprise receipt does not prove plan_complete=true")
    if receipt.get("production_claim") is not False:
        errors.append(
            "enterprise architecture planning receipt must not fabricate production readiness"
        )

    actual_contract_digest = _sha256(
        repo_root / "machine" / "enterprise_system_architecture.json"
    )
    if receipt.get("contract_digest") != actual_contract_digest:
        errors.append("enterprise contract digest mismatch")

    raw_files = contract.get("evidence_files")
    if not isinstance(raw_files, list):
        errors.append("enterprise evidence_files is invalid")
        raw_files = []

    actual_digests: dict[str, str] = {}
    for raw in sorted(raw_files):
        if not isinstance(raw, str) or not raw:
            errors.append("enterprise evidence file path is invalid")
            continue
        path = repo_root / raw
        if not path.is_file():
            errors.append(f"enterprise evidence file missing: {raw}")
            continue
        actual_digests[raw] = _sha256(path)

    claimed_digests = receipt.get("file_digests")
    if not isinstance(claimed_digests, dict):
        errors.append("enterprise receipt file_digests is invalid")
        claimed_digests = {}
    if actual_digests != claimed_digests:
        errors.append("enterprise independent file digest map mismatch")

    recomputed_evidence_digest = _digest_without(receipt, "evidence_digest")
    if receipt.get("evidence_digest") != recomputed_evidence_digest:
        errors.append("enterprise structural evidence digest mismatch")

    result: dict[str, Any] = {
        "schema_version": EXPECTED_SCHEMA,
        "verifier": "enterprise-system-architecture-independent-v1",
        "expected_head": expected_head,
        "valid": not errors,
        "errors": errors,
        "contract_digest": actual_contract_digest,
        "structural_evidence_digest": receipt.get("evidence_digest"),
        "recomputed_structural_evidence_digest": recomputed_evidence_digest,
        "receipt_digest": _sha256(receipt_path),
        "file_digests": actual_digests,
        "plan_complete": contract.get("plan_complete"),
        "production_claim": contract.get("production_claim"),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt")
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

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
            print("ERROR:", error)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
