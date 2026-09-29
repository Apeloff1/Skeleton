#!/usr/bin/env python3
"""Independent provider-neutral interaction protocol closure verifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
GAP_ID = "gap-provider-interaction-protocol"

SOURCE_TOKENS = {
    "skeleton/providers/contract.py": (
        "class FinishReason",
        "class ProviderDeltaKind",
        "class ProviderToolDefinition",
        "class ProviderToolCall",
        "class ProviderUsage",
        "class ProviderDelta",
    ),
    "skeleton/provider_runtime.py": (
        "provider_response_deltas",
        "_extract_provider_tool_calls",
        "_extract_provider_structured_output",
        "_normalized_provider_usage",
        "_normalized_finish_reason",
        "deadline exceeded",
    ),
    "skeleton/testing/test_provider_contract.py": (
        "test_sync_openai_accepts_tool_only_response_and_normalizes_call",
        "test_sync_openai_rejects_unoffered_tool_call",
        "test_sync_openai_normalizes_structured_output",
        "test_provider_usage_keeps_unknown_values_unknown",
        "test_normalized_response_decomposes_into_ordered_neutral_deltas",
        "test_default_provider_stream_uses_neutral_delta_contract",
    ),
    "skeleton/testing/test_provider_runtime_schema_parity.py": (
        "test_provider_protocol_enums_match_machine_schema",
        "test_provider_delta_machine_contract_matches_runtime_surface",
        "test_provider_request_response_schema_is_provider_native_free",
    ),
}

EXPECTED_DEPENDENCIES = {
    "gap-provider-surface-convergence",
    "gap-tool-runtime-convergence",
    "gap-governance-registry",
    "gap-cost-admission",
}


class VerificationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def find_entry(items: object, key: str, value: str) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    return next(
        (
            item
            for item in items
            if isinstance(item, dict) and item.get(key) == value
        ),
        None,
    )


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    digests: dict[str, str] = {}

    for rel, tokens in SOURCE_TOKENS.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"missing provider-protocol boundary: {rel}")
            continue
        source = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost provider-protocol token: {token}")
        digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    runtime = root / "skeleton/provider_runtime.py"
    mirror = root / "skeleton/ai/runtime/provider_runtime.py"
    if not mirror.is_file():
        errors.append("provider runtime AI mirror is missing")
    elif runtime.read_bytes() != mirror.read_bytes():
        errors.append("provider runtime AI mirror drifted")

    construction = load_json(root / "machine/ai_app_construction.json")
    handoff = load_json(root / "machine/ai_implementation_handoff.json")
    closure = load_json(root / "machine/ai_closure_evidence.json")

    gap = find_entry(construction.get("gap_register"), "id", GAP_ID)
    hand = find_entry(handoff.get("entries"), "gap", GAP_ID)
    evidence = find_entry(closure.get("entries"), "gap", GAP_ID)
    blueprint = construction.get("provider_interaction_protocol")

    if gap is None or gap.get("status") != "closed":
        errors.append("provider-interaction protocol gap is not closed")
    if not isinstance(blueprint, dict):
        errors.append("provider_interaction_protocol blueprint is missing")
    else:
        if blueprint.get("gap") != GAP_ID:
            errors.append("provider protocol blueprint gap binding is invalid")
        if blueprint.get("status") not in {"complete", "closed"}:
            errors.append("provider protocol blueprint is not complete")
        if blueprint.get("remaining") not in ([], None):
            errors.append("provider protocol blueprint still has remaining work")

    if hand is None:
        errors.append("provider protocol handoff is missing")
    else:
        if hand.get("implementation_status") != "closed":
            errors.append("provider protocol handoff is not closed")
        if set(hand.get("depends_on") or []) != EXPECTED_DEPENDENCIES:
            errors.append("provider protocol dependency graph mismatch")
        if hand.get("remaining") not in ([], None):
            errors.append("provider protocol handoff still has remaining work")

    if evidence is None:
        errors.append("provider protocol closure evidence is missing")
    else:
        for field in ("gap_status", "implementation_state", "closure_decision"):
            if evidence.get(field) != "closed":
                errors.append(f"provider protocol {field} is not closed")
        if evidence.get("outstanding_evidence") not in ([], None):
            errors.append("provider protocol evidence is still outstanding")
        if evidence.get("blockers") not in ([], None):
            errors.append("provider protocol closure still has blockers")
        present = evidence.get("evidence_present")
        if not isinstance(present, list) or len(present) < 8:
            errors.append("provider protocol executable evidence is incomplete")

    return {
        "schema_version": 1,
        "verifier": "independent-provider-protocol-v1",
        "gap_id": GAP_ID,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "boundary_digests": digests,
        "provider_mirror_digest": (
            hashlib.sha256(runtime.read_bytes()).hexdigest()
            if runtime.is_file() and mirror.is_file()
            else None
        ),
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        print(f"provider-protocol-closure: rejected: {exc}", file=sys.stderr)
        return 1
    if args.evidence_out:
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["valid"]:
        print("provider-protocol-closure: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f" - {error}", file=sys.stderr)
        return 1
    print(
        "provider-protocol-closure: OK "
        f"(boundaries={len(receipt['boundary_digests'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
