#!/usr/bin/env python3
"""Independent verifier for VOL-131 Internal Protocols.

The behavioral implementation lives in skeleton.distributed.network and is
mirrored byte-for-byte into skeleton.ai.runtime.distributed.network.  This
verifier intentionally does not import that implementation.  It inspects the
masterplan binding, AI-tree ownership mapping, source invariants, mirror parity,
and adversarial regression surface, then emits an exact-head evidence receipt.
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
CANONICAL = Path("skeleton/distributed/network/internal_protocol.py")
MIRROR = Path("skeleton/ai/runtime/distributed/network/internal_protocol.py")
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
            errors.append(
                f"{VOLUME} requirement invariant lost: {required}"
            )

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

    matches = [
        item
        for item in mappings
        if isinstance(item, dict)
        and item.get("source") == "skeleton/distributed/network"
        and item.get("destination")
        == "skeleton/ai/runtime/distributed/network"
    ]
    if len(matches) != 1:
        errors.append(
            "VOL-131 requires exactly one canonical distributed-network "
            "AI-tree mapping"
        )
        return {}

    mapping = matches[0]
    if mapping.get("kind") != "tree":
        errors.append("VOL-131 network AI-tree mapping must remain a tree")
    parity_mode = mapping.get("parity_mode", "exact")
    if parity_mode not in {"exact", None}:
        errors.append(
            "VOL-131 network AI-tree mapping must retain exact parity"
        )

    return {
        "mapping_id": mapping.get("id"),
        "source": mapping.get("source"),
        "destination": mapping.get("destination"),
        "kind": mapping.get("kind"),
        "parity_mode": parity_mode,
    }


def _verify_source(
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    paths = (CANONICAL, MIRROR, CANONICAL_INIT, MIRROR_INIT, TESTS)
    for relative in paths:
        if not (root / relative).is_file():
            errors.append(f"missing VOL-131 surface: {relative}")

    if errors:
        missing = [
            error for error in errors if error.startswith("missing VOL-131")
        ]
        if missing:
            return {}

    canonical_bytes = (root / CANONICAL).read_bytes()
    mirror_bytes = (root / MIRROR).read_bytes()
    if canonical_bytes != mirror_bytes:
        errors.append("VOL-131 canonical/AI protocol mirror drift")

    canonical_init = (root / CANONICAL_INIT).read_bytes()
    mirror_init = (root / MIRROR_INIT).read_bytes()
    if canonical_init != mirror_init:
        errors.append("VOL-131 canonical/AI network export drift")

    source = canonical_bytes.decode("utf-8")
    required_tokens = (
        "class TraceContext",
        "class ProtocolEnvelope",
        "class ProtocolReceipt",
        "class DeliverySemantics",
        "class UnknownOutcomePolicy",
        "correlation_id",
        "causation_id",
        "deadline_at_ms",
        "idempotency_key",
        "previous_envelope_digest",
        "def retry(",
        "def spawn_child(",
        "def trace_record(",
        "def validate_receipt(",
        "at_most_once delivery forbids protocol-level retries",
        "idempotent_retry requires idempotency_key",
        "retry attempt must bind previous_envelope_digest",
        "cannot retry expired envelope",
        "cannot spawn child after parent deadline",
        "receipt does not bind envelope digest",
        "protocol identity must be canonical JSON",
        "contains duplicate key",
    )
    for token in required_tokens:
        if token not in source:
            errors.append(
                f"VOL-131 implementation invariant missing: {token}"
            )

    test_source = (root / TESTS).read_text(encoding="utf-8")
    required_tests = (
        "test_protocol_digest_is_deterministic_across_attribute_order",
        "test_duplicate_protocol_attribute_is_rejected",
        "test_retry_preserves_operation_correlation_authority_and_deadline",
        "test_retry_chain_is_digest_bound_and_bounded",
        "test_retry_cannot_extend_or_cross_deadline",
        "test_retryable_delivery_requires_stable_idempotency_key",
        "test_child_envelope_binds_causation_and_trace_parentage",
        "test_trace_record_contains_identity_and_digests_not_payload_content",
        "test_receipt_binds_exact_envelope_and_trace_identity",
        "test_canonical_and_ai_runtime_protocol_files_are_byte_identical",
    )
    for name in required_tests:
        if name not in test_source:
            errors.append(f"VOL-131 regression missing: {name}")

    return {
        "canonical_digest": _sha256(root / CANONICAL),
        "mirror_digest": _sha256(root / MIRROR),
        "canonical_init_digest": _sha256(root / CANONICAL_INIT),
        "mirror_init_digest": _sha256(root / MIRROR_INIT),
        "test_digest": _sha256(root / TESTS),
        "required_invariant_count": len(required_tokens),
        "required_regression_count": len(required_tests),
        "mirror_parity": canonical_bytes == mirror_bytes,
        "export_parity": canonical_init == mirror_init,
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
        "schema_version": 1,
        "verifier": "independent-vol131-internal-protocols-v1",
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
            "schema_version": 1,
            "verifier": "independent-vol131-internal-protocols-v1",
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
