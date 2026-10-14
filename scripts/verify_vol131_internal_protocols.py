#!/usr/bin/env python3
"""Independent verifier for VOL-131 Internal Protocols.

The canonical message schema lives in skeleton.contracts.protocol and is
mirrored under skeleton.ai.runtime.contracts. The distributed-network layer may
add execution/retry/receipt behavior, but must not define a second
ProtocolEnvelope authority. This verifier never imports those implementations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
AI_TREE = Path("machine/ai_file_tree.json")
CONTRACT = Path("skeleton/contracts/protocol.py")
CONTRACT_MIRROR = Path("skeleton/ai/runtime/contracts/protocol.py")
EXECUTION = Path("skeleton/distributed/network/internal_protocol.py")
EXECUTION_MIRROR = Path(
    "skeleton/ai/runtime/distributed/network/internal_protocol.py"
)
CANONICAL_INIT = Path("skeleton/distributed/network/__init__.py")
MIRROR_INIT = Path("skeleton/ai/runtime/distributed/network/__init__.py")
TESTS = Path("skeleton/testing/test_internal_protocols.py")

VOLUME = "VOL-131"
TITLE = "Internal Protocols"
REQUIRED_GAPS = {
    "unify protocol envelopes",
    "bind protocols to tracing",
}
REQUIRED_REQUIREMENTS = (
    "Use stable envelopes with correlation, causation and deadline metadata.",
    "Specify retry/idempotency and unknown-outcome handling per operation class.",
)


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _find_volume(master: Mapping[str, Any]) -> Mapping[str, Any]:
    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise VerificationError("masterplan volumes must be a list")
    for volume in volumes:
        if isinstance(volume, dict) and volume.get("key") == VOLUME:
            return volume
    raise VerificationError(f"masterplan missing {VOLUME}")


def _verify_volume(
    master: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    volume = _find_volume(master)
    if volume.get("title") != TITLE:
        errors.append(f"{VOLUME} title drift")
    if volume.get("scope") != "canonical-plan":
        errors.append(f"{VOLUME} scope drift")
    if volume.get("completion_checkbox") is True:
        errors.append(f"{VOLUME} cannot self-sign from implementation evidence")

    gaps = set(volume.get("gaps") or [])
    missing_gaps = sorted(REQUIRED_GAPS - gaps)
    if missing_gaps:
        errors.append(
            f"{VOLUME} masterplan gap binding drift: {missing_gaps}"
        )
    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    for required in REQUIRED_REQUIREMENTS:
        if required not in requirements:
            errors.append(f"{VOLUME} requirement invariant lost: {required}")
    paths = set(str(item) for item in volume.get("implementation_paths") or [])
    if "skeleton/ai" not in paths:
        errors.append(f"{VOLUME} no longer binds skeleton/ai")
    if "skeleton/network" not in paths:
        errors.append(f"{VOLUME} no longer binds skeleton/network")
    return {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "scope": volume.get("scope"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "gaps": sorted(gaps),
    }


def _verify_ai_tree(
    manifest: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    mappings = manifest.get("mappings")
    if not isinstance(mappings, list):
        errors.append("AI file-tree mappings must be a list")
        return {}
    required = {
        (
            "skeleton/contracts",
            "skeleton/ai/runtime/contracts",
        ): "AIFT-CONTRACTS",
        (
            "skeleton/distributed/network",
            "skeleton/ai/runtime/distributed/network",
        ): "AIFT-NETWORK",
    }
    found: dict[str, dict[str, Any]] = {}
    for (source, destination), expected_id in required.items():
        matches = [
            item
            for item in mappings
            if isinstance(item, dict)
            and item.get("source") == source
            and item.get("destination") == destination
        ]
        if len(matches) != 1:
            errors.append(
                f"{VOLUME} requires exactly one {source} AI-tree mapping"
            )
            continue
        mapping = matches[0]
        if mapping.get("id") != expected_id:
            errors.append(f"{source} mapping identity drift")
        if mapping.get("kind") != "tree":
            errors.append(f"{source} mapping must remain a tree")
        found[expected_id] = {
            "source": source,
            "destination": destination,
            "kind": mapping.get("kind"),
        }
    return found


def _verify_source(root: Path, errors: list[str]) -> dict[str, Any]:
    paths = (
        CONTRACT,
        CONTRACT_MIRROR,
        EXECUTION,
        EXECUTION_MIRROR,
        CANONICAL_INIT,
        MIRROR_INIT,
        TESTS,
    )
    for relative in paths:
        if not (root / relative).is_file():
            errors.append(f"missing VOL-131 surface: {relative}")
    if any(error.startswith("missing VOL-131") for error in errors):
        return {}

    contract_bytes = (root / CONTRACT).read_bytes()
    contract_mirror_bytes = (root / CONTRACT_MIRROR).read_bytes()
    execution_bytes = (root / EXECUTION).read_bytes()
    execution_mirror_bytes = (root / EXECUTION_MIRROR).read_bytes()
    init_bytes = (root / CANONICAL_INIT).read_bytes()
    init_mirror_bytes = (root / MIRROR_INIT).read_bytes()

    if contract_bytes != contract_mirror_bytes:
        errors.append("VOL-131 canonical contract AI mirror drift")
    if execution_bytes != execution_mirror_bytes:
        errors.append("VOL-131 execution AI mirror drift")
    if init_bytes != init_mirror_bytes:
        errors.append("VOL-131 network export AI mirror drift")

    contract = contract_bytes.decode("utf-8")
    execution = execution_bytes.decode("utf-8")

    contract_tokens = (
        "class ProtocolEnvelope",
        "class ProtocolReplayGuard",
        "class RetryClass",
        "class UnknownOutcomePolicy",
        "PROTOCOL_ENVELOPE_VERSION",
        "correlation_id",
        "causation_id",
        "trace_id",
        "span_id",
        "deadline_utc",
        "idempotency_key",
        "unknown_outcome_policy",
        "def trace_headers(",
        "def deadline_exceeded(",
        "message_id replay changed canonical envelope content",
    )
    execution_tokens = (
        "from skeleton.contracts.protocol import (",
        "ProtocolEnvelope,",
        "class ProtocolExecutionEnvelope",
        "class ProtocolReceipt",
        "canonical_envelope_digest",
        "previous_execution_digest",
        "authority_digest",
        "max_attempts",
        "def retry(",
        "def spawn_child(",
        "def trace_record(",
        "def validate_receipt(",
        "RetryClass.NEVER requires one execution attempt",
        "retry attempt must bind previous_execution_digest",
        "cannot retry expired envelope",
        "cannot spawn child after parent deadline",
        "receipt does not bind canonical envelope digest",
        "receipt does not bind execution digest",
        "attributes contains duplicate key",
    )
    for token in contract_tokens:
        if token not in contract:
            errors.append(f"VOL-131 canonical invariant missing: {token}")
    for token in execution_tokens:
        if token not in execution:
            errors.append(f"VOL-131 execution invariant missing: {token}")
    if "class ProtocolEnvelope" in execution:
        errors.append(
            "VOL-131 execution layer defines a shadow ProtocolEnvelope authority"
        )

    tests = (root / TESTS).read_text(encoding="utf-8")
    required_tests = (
        "test_network_layer_uses_canonical_protocol_envelope",
        "test_execution_digest_is_deterministic_across_attribute_order",
        "test_duplicate_execution_attribute_is_rejected",
        "test_non_retryable_execution_is_single_attempt",
        "test_retryable_execution_requires_deadline_and_attempt_budget",
        "test_retry_preserves_canonical_authority_and_deadline",
        "test_retry_chain_is_digest_bound_and_bounded",
        "test_retry_cannot_cross_canonical_deadline",
        "test_child_preserves_operation_correlation_trace_tenant_and_authority",
        "test_trace_record_never_contains_raw_payload",
        "test_receipt_binds_canonical_and_execution_digests",
        "test_canonical_and_ai_runtime_protocol_execution_files_are_identical",
    )
    for name in required_tests:
        if name not in tests:
            errors.append(f"VOL-131 regression missing: {name}")

    return {
        "contract_digest": _sha256(root / CONTRACT),
        "contract_mirror_digest": _sha256(root / CONTRACT_MIRROR),
        "execution_digest": _sha256(root / EXECUTION),
        "execution_mirror_digest": _sha256(root / EXECUTION_MIRROR),
        "network_init_digest": _sha256(root / CANONICAL_INIT),
        "network_init_mirror_digest": _sha256(root / MIRROR_INIT),
        "test_digest": _sha256(root / TESTS),
        "required_invariant_count": len(contract_tokens) + len(execution_tokens),
        "required_regression_count": len(required_tests),
        "contract_mirror_parity": contract_bytes == contract_mirror_bytes,
        "mirror_parity": execution_bytes == execution_mirror_bytes,
        "export_parity": init_bytes == init_mirror_bytes,
        "single_envelope_authority": "class ProtocolEnvelope" not in execution,
    }


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    master = _load(root / MASTER)
    ai_tree = _load(root / AI_TREE)
    errors: list[str] = []
    volume_binding = _verify_volume(master, errors)
    ai_tree_binding = _verify_ai_tree(ai_tree, errors)
    implementation = _verify_source(root, errors)
    unique_errors = sorted(set(errors))
    receipt: dict[str, Any] = {
        "schema_version": 2,
        "verifier": "independent-vol131-internal-protocols-v2",
        "volume": VOLUME,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume_binding": volume_binding,
        "ai_tree_binding": ai_tree_binding,
        "implementation": implementation,
        "masterplan_digest": _sha256(root / MASTER),
        "ai_tree_digest": _sha256(root / AI_TREE),
        "errors": unique_errors,
        "valid": not unique_errors,
    }
    receipt["receipt_digest"] = _digest_json(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        receipt = {
            "schema_version": 2,
            "verifier": "independent-vol131-internal-protocols-v2",
            "volume": VOLUME,
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _digest_json(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-131 independent internal-protocol verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-131 independent internal-protocol verification: FAIL")
        for error in receipt.get("errors", []):
            print(f"- {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
