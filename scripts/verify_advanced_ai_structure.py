#!/usr/bin/env python3
"""Independent verifier for exact-head 100-level advanced AI evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "advanced_ai_structure_100.json"
EXPECTED_SCHEMA = "advanced-ai-structure/v1"
EXPECTED_VERIFIER = "advanced-ai-structure-structural-v1"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def _sha(path: Path) -> str:
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
    contract = _load(repo_root / "machine" / "advanced_ai_structure_100.json")

    if receipt.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("advanced AI receipt schema drifted")
    if receipt.get("verifier") != EXPECTED_VERIFIER:
        errors.append("advanced AI structural verifier identity drifted")
    if receipt.get("head_sha") != expected_head:
        errors.append("advanced AI receipt is not exact-head")
    if receipt.get("valid") is not True or receipt.get("errors"):
        errors.append("advanced AI structural validator did not close cleanly")
    if receipt.get("level_count") != 100:
        errors.append("advanced AI receipt does not prove 100 levels")
    if receipt.get("stratum_count") != 10:
        errors.append("advanced AI receipt does not prove 10 strata")
    if receipt.get("plan_complete") is not True:
        errors.append("advanced AI plan_complete was not proven")
    if receipt.get("implementation_claim") is not False:
        errors.append("advanced AI planning receipt fabricated implementation")

    actual_contract_digest = _sha(
        repo_root / "machine" / "advanced_ai_structure_100.json"
    )
    if receipt.get("contract_digest") != actual_contract_digest:
        errors.append("advanced AI contract digest mismatch")

    expected_files = [
        "machine/advanced_ai_structure_100.json",
        "machine/ai_app_construction.json",
        "machine/enterprise_system_architecture.json",
        "machine/architecture.json",
        "docs/plan/ADVANCED_AI_100_LEVELS.md",
        "docs/plan/AI_CHAT_MASTERPLAN_2026-10-06.md",
        "docs/AI_APP_CONSTRUCTION_MANUAL.md",
        "docs/ENTERPRISE_SYSTEM_ARCHITECTURE.md",
        "docs/ARCHITECTURE_MAP.md",
        "scripts/check_advanced_ai_structure.py",
        "scripts/verify_advanced_ai_structure.py",
        "tests/test_advanced_ai_structure.py",
        ".github/workflows/advanced-ai-structure.yml",
    ]
    actual_digests = {
        path: _sha(repo_root / path)
        for path in expected_files
        if (repo_root / path).is_file()
    }
    if receipt.get("file_digests") != actual_digests:
        errors.append("advanced AI independent file digest map mismatch")

    recomputed = _digest_without(receipt, "evidence_digest")
    if receipt.get("evidence_digest") != recomputed:
        errors.append("advanced AI evidence digest mismatch")

    if len(contract.get("levels") or []) != 100:
        errors.append("advanced AI contract no longer contains 100 levels")
    if len(contract.get("strata") or []) != 10:
        errors.append("advanced AI contract no longer contains 10 strata")
    if contract.get("completion", {}).get("promoted_levels") != []:
        errors.append("planning change pre-promoted levels")
    if contract.get("completion", {}).get("signed_levels") != []:
        errors.append("planning change pre-signed levels")

    result: dict[str, Any] = {
        "schema_version": EXPECTED_SCHEMA,
        "verifier": "advanced-ai-structure-independent-v1",
        "expected_head": expected_head,
        "valid": not errors,
        "errors": errors,
        "contract_digest": actual_contract_digest,
        "structural_evidence_digest": receipt.get("evidence_digest"),
        "recomputed_structural_evidence_digest": recomputed,
        "receipt_digest": _sha(receipt_path),
        "file_digests": actual_digests,
        "level_count": len(contract.get("levels") or []),
        "stratum_count": len(contract.get("strata") or []),
        "implementation_claim": contract.get("completion", {}).get(
            "implementation_claim"
        ),
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
