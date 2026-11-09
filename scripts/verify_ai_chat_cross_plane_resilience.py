#!/usr/bin/env python3
"""Independent exact-head rehasher for AI-chat cross-plane resilience."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_cross_plane_resilience.json"
SCHEMA = "ai-chat-cross-plane-resilience/v1"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rehash(payload: dict[str, object], field: str) -> str:
    value = dict(payload)
    value.pop(field, None)
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
    errors: list[str] = []
    receipt = _json(receipt_path)
    contract = _json(CONTRACT)

    if receipt.get("schema_version") != SCHEMA:
        errors.append("cross-plane receipt schema drifted")
    if receipt.get("verifier") != "ai-chat-cross-plane-resilience-structural-v1":
        errors.append("unexpected cross-plane structural verifier")
    if receipt.get("head_sha") != expected_head:
        errors.append("cross-plane receipt is not exact-head")
    if receipt.get("valid") is not True or receipt.get("errors"):
        errors.append("cross-plane structural verifier did not pass")
    if receipt.get("contract_digest") != _sha(CONTRACT):
        errors.append("cross-plane contract digest mismatch")

    files = contract.get("files")
    if not isinstance(files, dict):
        errors.append("cross-plane files contract invalid")
        files = {}

    actual = {
        str(role): _sha(ROOT / str(path))
        for role, path in sorted(files.items())
        if isinstance(path, str) and (ROOT / path).is_file()
    }
    if actual != receipt.get("digests"):
        errors.append("cross-plane file digest map mismatch")

    dependent_paths = (
        "machine/ai_chat_runtime_contract.json",
        "machine/ai_chat_model_routing.json",
        "machine/ai_chat_tool_recovery.json",
        "machine/ai_chat_attachments.json",
    )
    dependent = {
        path: _sha(ROOT / path)
        for path in dependent_paths
        if (ROOT / path).is_file()
    }
    if dependent != receipt.get("dependent_contract_digests"):
        errors.append("cross-plane dependent contract digest map mismatch")

    evidence_digest = receipt.get("evidence_digest")
    recomputed = _rehash(receipt, "evidence_digest")
    if evidence_digest != recomputed:
        errors.append("cross-plane evidence digest mismatch")

    canonical = ROOT / str(files.get("canonical_router", ""))
    mirror = ROOT / str(files.get("router_mirror", ""))
    if canonical.is_file() and mirror.is_file():
        if canonical.read_bytes() != mirror.read_bytes():
            errors.append("router mirror differs during independent verification")

    binding = ROOT / str(files.get("binding", ""))
    binding_digest = _sha(binding) if binding.is_file() else None
    tests = ROOT / str(files.get("tests", ""))
    test_digest = _sha(tests) if tests.is_file() else None

    result: dict[str, object] = {
        "schema_version": SCHEMA,
        "verifier": "independent-ai-chat-cross-plane-resilience-v1",
        "expected_head": expected_head,
        "valid": not errors,
        "errors": errors,
        "contract_digest": _sha(CONTRACT),
        "receipt_digest": _sha(receipt_path),
        "structural_evidence_digest": evidence_digest,
        "recomputed_structural_evidence_digest": recomputed,
        "file_digests": actual,
        "dependent_contract_digests": dependent,
        "binding_digest": binding_digest,
        "test_digest": test_digest,
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
            print("ERROR:", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
