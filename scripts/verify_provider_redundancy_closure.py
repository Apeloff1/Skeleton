#!/usr/bin/env python3
"""Independent verifier for the P1 provider-redundancy implementation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_RUNTIME_TOKENS = (
    "class FailoverProviderAdapter(ProviderAdapter):",
    "class ProviderProtocolViolationError(ProviderInvocationError):",
    "class OpenAICompatibleSecondaryAdapter(OpenAIProviderAdapter):",
    "AI_SECONDARY_API_KEY",
    "AI_SECONDARY_BASE_URL",
    "AI_SECONDARY_MODEL",
    "secondary provider must use a distinct provider hostname",
    "except ProviderPolicyError:",
    "except ProviderProtocolViolationError:",
    "except ProviderUnavailableError as exc:",
    "except ProviderInvocationError as exc:",
    "def redundancy_status(",
    "failover_successes",
    "secondary provider capability is not declared: image-generation",
)

REQUIRED_TEST_TOKENS = (
    "test_failover_provider_uses_primary_without_touching_secondary",
    "test_failover_provider_routes_invocation_failure_to_secondary_model",
    "test_failover_provider_skips_unavailable_primary",
    "test_failover_provider_never_routes_policy_denial",
    "test_malformed_provider_json_is_terminal_protocol_violation",
    "test_failover_provider_never_routes_protocol_violation",
    "test_failover_provider_never_routes_invalid_request_protocol",
    "test_failover_provider_does_not_remap_explicit_nonprimary_model",
    "test_provider_registry_returns_failover_adapter_and_exposes_routing",
    "test_provider_registry_readiness_fails_closed_on_invalid_fallback_receipt",
    "test_provider_registry_readiness_fails_closed_on_invalid_active_receipt",
    "test_provider_registry_status_suppresses_invalid_receipt_availability",
    "test_provider_registry_secondary_configuration_fails_closed_when_partial",
    "test_provider_registry_rejects_secondary_on_primary_hostname",
    "test_declared_secondary_adapter_denies_undeclared_media_capabilities",
)


class VerificationError(RuntimeError):
    pass


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    runtime = root / "skeleton/provider_runtime.py"
    mirror = root / "skeleton/ai/runtime/provider_runtime.py"
    tests = root / "skeleton/testing/test_provider_contract.py"
    construction_path = root / "machine/ai_app_construction.json"

    runtime_source = _text(runtime)
    mirror_source = _text(mirror)
    test_source = _text(tests)

    for token in REQUIRED_RUNTIME_TOKENS:
        if token not in runtime_source:
            errors.append(f"provider runtime lost redundancy token: {token}")
    for token in REQUIRED_TEST_TOKENS:
        if token not in test_source:
            errors.append(f"provider tests lost redundancy token: {token}")
    if runtime_source != mirror_source:
        errors.append("canonical provider runtime mirror drift")

    construction = _json(construction_path)
    declared = construction.get("runtime_model_providers")
    declaration = None
    if isinstance(declared, list):
        declaration = next(
            (
                item
                for item in declared
                if isinstance(item, dict)
                and item.get("id") == "openai-compatible-secondary"
            ),
            None,
        )
    if declaration is None:
        errors.append("secondary runtime provider declaration is missing")
    else:
        for key in (
            "architecture_read_required",
            "construction_manual_read_required",
            "activation_receipt_required",
        ):
            if declaration.get(key) is not True:
                errors.append(f"secondary provider lost {key}")
        capabilities = declaration.get("capabilities")
        if capabilities != ["text-generation"]:
            errors.append("secondary provider capability declaration is not text-only")
        credentials = declaration.get("credentials")
        if credentials != ["AI_SECONDARY_API_KEY"]:
            errors.append("secondary provider credential ownership drift")

    blueprint = construction.get("provider_redundancy_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("provider_redundancy_blueprint is missing")
    else:
        if blueprint.get("status") != "closed":
            errors.append("provider redundancy blueprint must remain closed")
        if blueprint.get("gap") != "gap-provider-redundancy":
            errors.append("provider redundancy blueprint gap binding is invalid")
        routing = blueprint.get("routing")
        if not isinstance(routing, dict):
            errors.append("provider redundancy routing contract is missing")
        else:
            if set(routing.get("failover_on") or []) != {
                "ProviderUnavailableError",
                "ProviderInvocationError",
            }:
                errors.append("provider redundancy failover classes drifted")
            never = set(routing.get("never_failover_on") or [])
            if "ProviderPolicyError" not in never:
                errors.append("provider policy denial is no longer fail-closed")

    gap_register = construction.get("gap_register")
    gap = None
    if isinstance(gap_register, list):
        gap = next(
            (
                item
                for item in gap_register
                if isinstance(item, dict)
                and item.get("id") == "gap-provider-redundancy"
            ),
            None,
        )
    if gap is None:
        errors.append("provider redundancy gap is missing")
    elif gap.get("status") != "closed":
        errors.append("provider redundancy gap must remain closed")

    return {
        "schema_version": 1,
        "verifier": "independent-provider-redundancy-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "runtime_digest": hashlib.sha256(
            runtime_source.encode("utf-8")
        ).hexdigest(),
        "mirror_digest": hashlib.sha256(
            mirror_source.encode("utf-8")
        ).hexdigest(),
        "test_digest": hashlib.sha256(
            test_source.encode("utf-8")
        ).hexdigest(),
        "declared_secondary": declaration is not None,
        "gap_status": None if gap is None else gap.get("status"),
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
        print(f"provider-redundancy: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("provider-redundancy: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "provider-redundancy: OK "
        f"(secondary={receipt['declared_secondary']}, "
        f"gap={receipt['gap_status']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
