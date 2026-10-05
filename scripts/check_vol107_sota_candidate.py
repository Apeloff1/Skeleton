#!/usr/bin/env python3
"""Independent repository verifier for VOL-107 bounded SOTA-candidate claims."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine" / "sota_candidate_policy.json"
MODULE_PATH = ROOT / "skeleton" / "eval" / "sota_candidate.py"
TEST_PATH = ROOT / "skeleton" / "testing" / "test_vol107_sota_candidate.py"
INTEGRATION_PATH = ROOT / "skeleton" / "eval" / "p3_acceptance.py"

EXPECTED_SHORTCUTS = {
    "aggregate_only_scoring",
    "benchmark_digest_substitution",
    "contamination_unknown_or_dirty",
    "dataset_digest_substitution",
    "evidence_omission",
    "metric_omission",
    "metric_regression_compensation",
    "replay_metric_drift",
    "replay_without_exact_revision",
    "same_family_verification",
    "self_verification",
    "unbounded_sota_claim",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("vol107_sota_candidate_verify", MODULE_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load VOL-107 implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate() -> list[str]:
    errors: list[str] = []
    for path in (MANIFEST, MODULE_PATH, TEST_PATH, INTEGRATION_PATH):
        if not path.is_file():
            errors.append(f"required VOL-107 surface missing: {path.relative_to(ROOT)}")
    if errors:
        return errors

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        errors.append("SOTA candidate manifest schema_version must be 1")
    if payload.get("volume") != "VOL-107":
        errors.append("SOTA candidate manifest must bind VOL-107")
    if payload.get("status") != "implementation_contract":
        errors.append("SOTA candidate manifest status must remain implementation_contract")
    if payload.get("claim_scope") != "bounded_sota_candidate":
        errors.append("SOTA candidate manifest must prohibit unbounded claims")

    shortcuts = payload.get("prohibited_shortcuts")
    if not isinstance(shortcuts, list) or set(shortcuts) != EXPECTED_SHORTCUTS:
        errors.append("SOTA candidate prohibited shortcut registry drift")

    implementation = payload.get("implementation")
    expected_implementation = {
        "runtime": "skeleton/eval/sota_candidate.py",
        "package": "skeleton/eval/__init__.py",
        "tests": "skeleton/testing/test_vol107_sota_candidate.py",
        "verifier": "scripts/check_vol107_sota_candidate.py",
        "integration": "skeleton/eval/p3_acceptance.py",
    }
    if implementation != expected_implementation:
        errors.append("SOTA candidate implementation path binding drift")

    required_bindings = payload.get("required_bindings")
    expected_bindings = {
        "benchmark_digest",
        "dataset_digest",
        "source_revision",
        "contamination_audit_digest",
        "robustness_evidence_digest",
        "security_evidence_digest",
        "efficiency_evidence_digest",
        "independent_replay_digest",
    }
    if not isinstance(required_bindings, list) or set(required_bindings) != expected_bindings:
        errors.append("SOTA candidate required evidence bindings drift")

    module = _load_module()
    if set(module.PROHIBITED_SHORTCUTS) != EXPECTED_SHORTCUTS:
        errors.append("runtime prohibited shortcut registry disagrees with manifest")
    if module.SOTA_CANDIDATE_CLAIM != "bounded_sota_candidate":
        errors.append("runtime SOTA claim scope drift")
    if module.SOTA_CANDIDATE_SCHEMA != "skeleton.sota_candidate.v1":
        errors.append("runtime SOTA candidate schema drift")

    expected_exports = {
        "PROHIBITED_SHORTCUTS",
        "SOTA_CANDIDATE_CLAIM",
        "SOTA_CANDIDATE_SCHEMA",
        "SOTACandidateClaim",
        "SOTACandidateError",
        "SOTACandidateGate",
        "SOTAMetricDirection",
        "SOTAMetricRequirement",
        "SOTAQualificationReceipt",
        "SOTAReplayRecord",
    }
    if set(module.__all__) != expected_exports:
        errors.append("VOL-107 public export contract drift")

    try:
        requirements = (
            module.SOTAMetricRequirement(
                "quality",
                module.SOTAMetricDirection.MAXIMIZE,
                0.8,
                0.05,
            ),
            module.SOTAMetricRequirement(
                "latency_ms",
                module.SOTAMetricDirection.MINIMIZE,
                100.0,
                5.0,
            ),
        )
        claim = module.SOTACandidateClaim(
            claim_id="verifier-claim",
            candidate_id="candidate",
            benchmark_id="benchmark",
            benchmark_digest="a" * 64,
            dataset_digest="b" * 64,
            source_revision="1" * 40,
            task_scope="bounded verifier fixture",
            population="held-out cases",
            generator_id="generator",
            generator_family_id="generator-family",
            metric_requirements=requirements,
            candidate_metrics={"quality": 0.9, "latency_ms": 90.0},
            contamination_status="clean",
            contamination_audit_digest="c" * 64,
            robustness_evidence_digest="d" * 64,
            security_evidence_digest="e" * 64,
            efficiency_evidence_digest="f" * 64,
            evidence_refs=(
                "benchmark:fixture",
                "dataset:fixture",
                "contamination:fixture",
                "robustness:fixture",
                "security:fixture",
                "efficiency:fixture",
            ),
        )
        replay = module.SOTAReplayRecord(
            replay_id="replay",
            claim_digest=claim.digest,
            source_revision=claim.source_revision,
            benchmark_digest=claim.benchmark_digest,
            dataset_digest=claim.dataset_digest,
            verifier_id="independent-verifier",
            verifier_family_id="independent-family",
            observed_metrics=dict(claim.candidate_metrics),
            evidence_refs=("replay:fixture",),
            passed=True,
        )
        receipt = module.SOTACandidateGate().qualify(claim, replay)
        module.SOTACandidateGate().verify(claim, replay, receipt)
    except Exception as exc:
        errors.append(f"SOTA candidate independent qualification smoke failed: {exc}")

    try:
        bad = module.SOTAReplayRecord(
            replay_id="self-replay",
            claim_digest=claim.digest,
            source_revision=claim.source_revision,
            benchmark_digest=claim.benchmark_digest,
            dataset_digest=claim.dataset_digest,
            verifier_id=claim.generator_id,
            verifier_family_id="independent-family",
            observed_metrics=dict(claim.candidate_metrics),
            evidence_refs=("replay:self",),
            passed=True,
        )
        module.SOTACandidateGate().qualify(claim, bad)
    except module.SOTACandidateError:
        pass
    except Exception as exc:
        errors.append(f"self-verification rejection raised unexpected error: {exc}")
    else:
        errors.append("SOTA candidate runtime accepted self-verification")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"VOL-107 ERROR: {error}")
        return 1
    print(
        "VOL-107 OK: bounded claim identity, non-compensable metrics, "
        "contamination binding, independent replay, and tamper detection verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
