#!/usr/bin/env python3
"""Independent repository verifier for VOL-071 Specialized Intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine/ai_domain_registry.json"
MODULE_PATH = ROOT / "skeleton/ai/specialization/domain_registry.py"
TEST_PATH = ROOT / "tests/test_vol071_specialized_intelligence.py"

EXPECTED_DOMAINS = {
    "software-engineering",
    "simulation-intelligence",
    "research-synthesis",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("vol071_domain_registry_verify", MODULE_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load VOL-071 implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate() -> list[str]:
    errors: list[str] = []
    for path in (MANIFEST, MODULE_PATH, TEST_PATH):
        if not path.is_file():
            errors.append(f"required VOL-071 surface missing: {path.relative_to(ROOT)}")
    if errors:
        return errors

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        errors.append("domain registry schema_version must be 1")
    if payload.get("volume") != "VOL-071":
        errors.append("domain registry must bind VOL-071")
    if payload.get("status") != "implementation_contract":
        errors.append("domain registry status must remain implementation_contract before promotion")

    policy = payload.get("policy")
    if not isinstance(policy, dict):
        errors.append("domain registry policy must be an object")
    else:
        for key in ("routing_rule", "fallback_rule", "evaluation_rule"):
            if not isinstance(policy.get(key), str) or not policy[key].strip():
                errors.append(f"domain registry policy missing {key}")

    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        return errors + ["domain registry profiles must be a list"]
    domain_ids = {
        item.get("domain_id")
        for item in profiles
        if isinstance(item, dict) and isinstance(item.get("domain_id"), str)
    }
    if domain_ids != EXPECTED_DOMAINS:
        errors.append("domain registry must exactly cover the initial governed domains")

    for item in profiles:
        if not isinstance(item, dict):
            errors.append("domain registry profile must be an object")
            continue
        evaluation = item.get("evaluation")
        if not isinstance(evaluation, dict):
            errors.append(f"{item.get('domain_id')} evaluation ownership missing")
            continue
        if evaluation.get("owner_id") == item.get("domain_id"):
            errors.append(f"{item.get('domain_id')} cannot self-own evaluation")
        required_tools = set(item.get("required_tools", []))
        allowed_tools = set(item.get("allowed_tools", []))
        if not required_tools.issubset(allowed_tools):
            errors.append(f"{item.get('domain_id')} required tools escape allowlist")
        if not item.get("required_source_types"):
            errors.append(f"{item.get('domain_id')} must declare required source types")
        if not item.get("forbidden_assumptions"):
            errors.append(f"{item.get('domain_id')} must declare forbidden assumptions")

    module = _load_module()
    required_exports = {
        "CandidateRejection",
        "DomainProfile",
        "DomainRegistry",
        "EvaluationOwnership",
        "RoutingDecision",
        "SpecialistCandidate",
        "SpecialistEvaluation",
        "SpecializationError",
        "SpecializedRoute",
    }
    if set(module.__all__) != required_exports:
        errors.append("VOL-071 public export contract drift")

    try:
        registry = module.DomainRegistry.from_manifest(MANIFEST)
    except Exception as exc:
        errors.append(f"domain registry cannot be instantiated: {exc}")
        return errors

    if set(registry.domain_ids) != EXPECTED_DOMAINS:
        errors.append("runtime domain IDs disagree with machine registry")
    if len(registry.registry_digest) != 64:
        errors.append("runtime registry digest must be sha256")

    try:
        fallback = registry.route(
            "unknown-domain",
            (),
            (),
            now=datetime(2026, 10, 5, tzinfo=timezone.utc),
        )
        registry.verify(fallback)
        if fallback.decision.value != "general_fallback":
            errors.append("unknown domains must fall back to general capability")
    except Exception as exc:
        errors.append(f"general fallback smoke contract failed: {exc}")

    implementation = payload.get("implementation", {})
    expected_paths = {
        "registry": "skeleton/ai/specialization/domain_registry.py",
        "tests": "tests/test_vol071_specialized_intelligence.py",
        "verifier": "scripts/check_vol071_specialized_intelligence.py",
    }
    if implementation != expected_paths:
        errors.append("machine implementation path binding drift")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"VOL-071 ERROR: {error}")
        return 1
    print(
        "VOL-071 OK: governed domains, explicit eval ownership, source/tool policy, "
        "fallback semantics, deterministic routing receipt, and implementation bindings verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
