#!/usr/bin/env python3
"""Build exact-head evidence candidates for P1 learning/evaluation gap batch 3.

This verifier is deliberately non-authoritative. It proves a bounded set of
canonical P1 learning/evaluation gaps against repository-owned contracts,
registries, validators, workflows, and regressions. It never writes EVID-04
bindings, clears masterplan gaps, signs accountability, or changes maturity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_p1_risk_evidence import (  # noqa: E402
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
)


_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
CATEGORY = "learning_eval_gap_closure"
BATCH_ID = "p1-learning-eval-gap-batch3"


class LearningEvalGapEvidenceError(RuntimeError):
    """Learning/evaluation gap evidence inputs are malformed or incomplete."""


COVERAGE: dict[tuple[str, str], dict[str, Any]] = {
    (
        "VOL-077",
        "define experiment schema",
    ): {
        "sources": [
            "skeleton/eval/experiment_registry.py",
            "machine/p1_experiment_registry.json",
            "scripts/check_p1_experiment_registry.py",
        ],
        "tests": [
            "skeleton/testing/test_experiment_registry.py",
            "tests/test_p1_experiment_registry.py",
        ],
        "markers": {
            "skeleton/eval/experiment_registry.py": [
                "EXPERIMENT_SCHEMA_VERSION = 1",
                "class ExperimentManifest:",
                "class ExperimentRegistry:",
            ],
            "scripts/check_p1_experiment_registry.py": [
                '"immutable_experiment_identity": True',
                "def load_registry(",
            ],
            "tests/test_p1_experiment_registry.py": [
                "test_canonical_machine_registry_starts_empty_and_valid",
                "test_existing_experiment_identity_is_immutable",
            ],
        },
    },
    (
        "VOL-077",
        "bind experiments to reproducibility/provenance",
    ): {
        "sources": [
            "skeleton/eval/experiment_registry.py",
            "scripts/check_p1_experiment_registry.py",
            ".github/workflows/p1-experiment-registry.yml",
        ],
        "tests": [
            "skeleton/testing/test_experiment_registry.py",
            "tests/test_p1_experiment_registry.py",
        ],
        "markers": {
            "skeleton/eval/experiment_registry.py": [
                "source_commit: str",
                "def registry_evidence_ref(",
                '"production_authority": False',
            ],
            ".github/workflows/p1-experiment-registry.yml": [
                "Emit exact-head LEARN-01 evidence receipt",
                "--task-id P1-LEARN-01",
                "--accountability-id ACC-P1-LEARN-01",
            ],
            "skeleton/testing/test_experiment_registry.py": [
                "test_manifest_is_deterministic_and_non_authoritative",
                "test_source_commit_is_exact_and_hypothesis_is_normalized",
            ],
        },
    },
    (
        "VOL-082",
        "define canonical benchmark registry",
    ): {
        "sources": [
            "skeleton/eval/benchmark_registry.py",
            "machine/p1_benchmark_registry.json",
            "scripts/check_p1_benchmark_registry.py",
        ],
        "tests": [
            "skeleton/testing/test_benchmark_registry.py",
            "tests/test_p1_benchmark_registry.py",
        ],
        "markers": {
            "skeleton/eval/benchmark_registry.py": [
                "BENCHMARK_REGISTRY_SCHEMA_VERSION = 1",
                "class BenchmarkManifest:",
                "class BenchmarkRegistry:",
            ],
            "tests/test_p1_benchmark_registry.py": [
                "test_repository_registry_is_valid_and_non_authoritative",
                "test_existing_benchmark_identity_cannot_mutate",
            ],
        },
    },
    (
        "VOL-082",
        "bind benchmark claims to reproducibility records",
    ): {
        "sources": [
            "skeleton/eval/benchmark_registry.py",
            "skeleton/contracts/reproducibility.py",
            ".github/workflows/p1-benchmark-registry.yml",
        ],
        "tests": [
            "skeleton/testing/test_benchmark_registry.py",
            "tests/test_p1_benchmark_registry.py",
        ],
        "markers": {
            "skeleton/eval/benchmark_registry.py": [
                "reproducibility_bundle_digest: str",
                "def qualify_benchmark(",
                "def evaluate_improvement_claim(",
                "contamination_evidence",
            ],
            "skeleton/testing/test_benchmark_registry.py": [
                "test_experiment_and_reproducibility_substitution_block",
                "test_experiment_source_commit_must_match_reproducibility",
                "test_improvement_claim_accepts_independent_better_candidate",
            ],
        },
    },
    (
        "VOL-324",
        "seed historical failure cases",
    ): {
        "sources": [
            "skeleton/eval/regression_corpus.py",
            "machine/p1_regression_corpus.json",
            "scripts/check_p1_regression_corpus.py",
        ],
        "tests": [
            "skeleton/testing/test_regression_corpus.py",
            "tests/test_p1_regression_corpus.py",
        ],
        "markers": {
            "skeleton/eval/regression_corpus.py": [
                "class RegressionCase:",
                "class RegressionCorpus:",
                "class FailureClass(str, Enum):",
            ],
            "tests/test_p1_regression_corpus.py": [
                "test_repository_corpus_is_valid_and_seeded",
                "test_existing_case_cannot_be_removed",
            ],
        },
    },
    (
        "VOL-324",
        "bind promotion gates",
    ): {
        "sources": [
            "skeleton/eval/regression_corpus.py",
            "skeleton/contracts/risk_evidence.py",
            ".github/workflows/p1-regression-corpus.yml",
        ],
        "tests": [
            "skeleton/testing/test_regression_corpus.py",
            "tests/test_p1_regression_corpus.py",
        ],
        "markers": {
            "skeleton/eval/regression_corpus.py": [
                "promotion_blocking: bool = True",
                "def qualify_regression_corpus(",
                "risk_obligation_id: str",
                "def accepted_evidence_ref(self) -> EvidenceRef:",
            ],
            "skeleton/testing/test_regression_corpus.py": [
                "test_missing_case_blocks_promotion",
                "test_reappearing_known_failure_blocks_promotion",
                "test_missing_or_unresolved_evid04_binding_blocks",
                "test_case_must_remain_promotion_blocking",
            ],
        },
    },
    (
        "VOL-414",
        "define eligibility/redaction",
    ): {
        "sources": [
            "skeleton/eval/shadow_traffic.py",
            "skeleton/eval/experiment_registry.py",
            ".github/workflows/p1-shadow-traffic-isolation.yml",
        ],
        "tests": [
            "skeleton/testing/test_shadow_traffic.py",
        ],
        "markers": {
            "skeleton/eval/shadow_traffic.py": [
                "class ShadowInputReceipt:",
                "redacted_input_digest: str",
                "class ShadowPolicy:",
                "def qualify_shadow_traffic(",
            ],
            "skeleton/testing/test_shadow_traffic.py": [
                "test_sensitive_input_requires_real_redaction",
                "test_fraction_data_class_and_tenant_eligibility_fail_closed",
                "test_policy_cannot_enable_shadow_side_effects",
            ],
        },
    },
    (
        "VOL-414",
        "bind champion/challenger",
    ): {
        "sources": [
            "skeleton/eval/shadow_traffic.py",
            "skeleton/eval/champion_registry.py",
            ".github/workflows/p1-shadow-traffic-isolation.yml",
        ],
        "tests": [
            "skeleton/testing/test_shadow_traffic.py",
            "skeleton/testing/test_champion_registry.py",
        ],
        "markers": {
            "skeleton/eval/shadow_traffic.py": [
                "registry: ChampionRegistry",
                "candidate: CandidateArtifact",
                "champion_registry_digest=registry.registry_digest",
            ],
            "skeleton/testing/test_shadow_traffic.py": [
                "test_current_champion_cannot_be_shadow_challenger",
                "test_unregistered_candidate_is_rejected",
                "test_champion_and_registry_mutation_block",
            ],
        },
    },
    (
        "VOL-415",
        "unify self-improvement registry",
    ): {
        "sources": [
            "skeleton/eval/champion_registry.py",
            "machine/p1_champion_registry.json",
            "scripts/check_p1_champion_registry.py",
        ],
        "tests": [
            "skeleton/testing/test_champion_registry.py",
            "tests/test_p1_champion_registry.py",
        ],
        "markers": {
            "skeleton/eval/champion_registry.py": [
                "class ChampionRegistry:",
                "class CandidateArtifact:",
                "def current_champion_digest(self) -> str:",
                "def registry_digest(self) -> str:",
            ],
            "scripts/check_p1_champion_registry.py": [
                '"candidate_self_promotion": False',
                '"immutable_candidate_identity": True',
                '"immutable_initial_champion": True',
            ],
            "tests/test_p1_champion_registry.py": [
                "test_initial_champion_cannot_be_rewritten",
                "test_existing_candidate_cannot_be_deleted",
                "test_transition_history_cannot_be_rewritten",
            ],
        },
    },
    (
        "VOL-415",
        "bind release gates",
    ): {
        "sources": [
            "skeleton/eval/champion_registry.py",
            "skeleton/eval/benchmark_registry.py",
            "skeleton/contracts/reproducibility.py",
            ".github/workflows/p1-champion-registry.yml",
        ],
        "tests": [
            "skeleton/testing/test_champion_registry.py",
            "tests/test_p1_champion_registry.py",
        ],
        "markers": {
            "skeleton/eval/champion_registry.py": [
                "def qualify_candidate_artifact(",
                "def evaluate_promotion(",
                "def apply_promotion(",
                "class PromotionDecision:",
            ],
            ".github/workflows/p1-champion-registry.yml": [
                "Build accepted LEARN-03 promotion evidence",
                "Emit exact-head LEARN-03 evidence receipt",
            ],
            "skeleton/testing/test_champion_registry.py": [
                "test_candidate_artifact_qualification_binds_all_upstream_evidence",
                "test_accepted_comparative_promotion_is_append_only",
                "test_non_improvement_cannot_advance_champion",
            ],
        },
    },
    (
        "VOL-419",
        "ingest incidents/negative results",
    ): {
        "sources": [
            "skeleton/eval/failure_knowledge.py",
            "machine/p1_failure_knowledge.json",
            "scripts/check_p1_failure_knowledge.py",
        ],
        "tests": [
            "skeleton/testing/test_failure_knowledge.py",
            "tests/test_p1_failure_knowledge.py",
        ],
        "markers": {
            "skeleton/eval/failure_knowledge.py": [
                "class FailureSourceKind(str, Enum):",
                "class FailureKnowledgeRecord:",
                "class FailureKnowledgeLedger:",
            ],
            "tests/test_p1_failure_knowledge.py": [
                "test_repository_failure_knowledge_is_valid",
                "test_existing_record_cannot_mutate",
                "test_existing_record_cannot_be_removed",
            ],
        },
    },
    (
        "VOL-419",
        "bind risk/test generation",
    ): {
        "sources": [
            "skeleton/eval/failure_knowledge.py",
            "skeleton/eval/regression_corpus.py",
            "skeleton/contracts/risk_evidence.py",
            ".github/workflows/p1-failure-knowledge.yml",
        ],
        "tests": [
            "skeleton/testing/test_failure_knowledge.py",
            "tests/test_p1_failure_knowledge.py",
        ],
        "markers": {
            "skeleton/eval/failure_knowledge.py": [
                "risk_obligation_id: str",
                "risk_obligation_digest: str",
                "def learning_signal_for(",
                "def qualify_failure_knowledge(",
            ],
            "skeleton/testing/test_failure_knowledge.py": [
                "test_missing_unresolved_or_nonblocking_risk_fails",
                "test_learning_signal_has_no_production_or_self_modify_authority",
                "test_rejected_failure_knowledge_cannot_materialize_evidence",
            ],
        },
    },
}


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LearningEvalGapEvidenceError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise LearningEvalGapEvidenceError(f"{path} must contain an object")
    return payload


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return _digest_bytes(raw)


def _validate_spec_paths(
    root: Path,
    spec: dict[str, Any],
) -> tuple[list[Path], list[Path]]:
    source_paths = [root / item for item in spec["sources"]]
    test_paths = [root / item for item in spec["tests"]]
    for path in source_paths + test_paths:
        if not path.is_file():
            raise LearningEvalGapEvidenceError(
                f"evidence path is missing: {path.relative_to(root)}"
            )
    return source_paths, test_paths


def _validate_markers(
    root: Path,
    spec: dict[str, Any],
    volume_key: str,
) -> None:
    markers = spec.get("markers")
    if not isinstance(markers, dict) or not markers:
        raise LearningEvalGapEvidenceError(
            f"{volume_key}: marker map is empty"
        )
    declared = set(spec["sources"]) | set(spec["tests"])
    for relative, required in markers.items():
        if relative not in declared:
            raise LearningEvalGapEvidenceError(
                f"{volume_key}: marker path is not declared evidence: {relative}"
            )
        if not isinstance(required, list) or not required:
            raise LearningEvalGapEvidenceError(
                f"{volume_key}: marker list is empty for {relative}"
            )
        text = (root / relative).read_text(encoding="utf-8")
        missing = [marker for marker in required if marker not in text]
        if missing:
            raise LearningEvalGapEvidenceError(
                f"{volume_key}: {relative} missing contract markers: "
                + ",".join(missing)
            )


def build_learning_eval_gap_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise LearningEvalGapEvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    canonical_paths = {
        "master_plan": root / MASTER,
        "p1_execution_map": root / P1_MAP,
        "adversarial_closure": root / ADVERSARIAL,
        "risk_policy": root / POLICY,
        "risk_registry": root / REGISTRY,
    }
    before = {
        name: _digest_file(path)
        for name, path in canonical_paths.items()
    }

    master = _load(canonical_paths["master_plan"])
    p1_map = _load(canonical_paths["p1_execution_map"])
    adversarial = _load(canonical_paths["adversarial_closure"])
    policy = _load(canonical_paths["risk_policy"])
    registry = _load(canonical_paths["risk_registry"])

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    gap_by_identity = {
        (
            obligation.source_ref.split(":", 1)[0],
            obligation.statement,
        ): obligation
        for obligation in obligations
        if obligation.kind is RiskKind.GAP
    }

    registry_rows = registry.get("records")
    if not isinstance(registry_rows, list):
        raise LearningEvalGapEvidenceError(
            "risk registry records must be a list"
        )
    bound_ids: set[str] = set()
    for index, row in enumerate(registry_rows):
        if not isinstance(row, dict):
            raise LearningEvalGapEvidenceError(
                f"risk registry record {index} must be an object"
            )
        obligation_id = row.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id:
            raise LearningEvalGapEvidenceError(
                f"risk registry record {index} has invalid obligation_id"
            )
        if obligation_id in bound_ids:
            raise LearningEvalGapEvidenceError(
                f"duplicate governed binding identity: {obligation_id}"
            )
        bound_ids.add(obligation_id)

    known_ids = {item.obligation_id for item in obligations}
    unknown_ids = sorted(bound_ids - known_ids)
    if unknown_ids:
        raise LearningEvalGapEvidenceError(
            "risk registry references unknown obligations: "
            + ",".join(unknown_ids)
        )

    records: list[dict[str, Any]] = []
    for identity in sorted(COVERAGE):
        volume_key, statement = identity
        obligation = gap_by_identity.get(identity)
        if obligation is None:
            raise LearningEvalGapEvidenceError(
                f"missing canonical gap obligation: {volume_key}: {statement}"
            )
        spec = COVERAGE[identity]
        source_paths, test_paths = _validate_spec_paths(root, spec)
        _validate_markers(root, spec, volume_key)

        packet: dict[str, Any] = {
            "batch_id": BATCH_ID,
            "volume_key": volume_key,
            "statement": statement,
            "obligation_id": obligation.obligation_id,
            "obligation_digest": obligation.obligation_digest,
            "source_ref": obligation.source_ref,
            "expected_head": expected_head,
            "source_digests": {
                str(path.relative_to(root)): _digest_file(path)
                for path in source_paths
            },
            "test_digests": {
                str(path.relative_to(root)): _digest_file(path)
                for path in test_paths
            },
            "verified_contract_markers": {
                path: list(markers)
                for path, markers in sorted(spec["markers"].items())
            },
            "binding_present": obligation.obligation_id in bound_ids,
            "non_authoritative": True,
            "creates_binding": False,
            "clears_masterplan_gap": False,
            "signs_accountability": False,
            "promotes_maturity": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packet["candidate_evidence_ref"] = {
            "source": (
                f"p1:learning-eval-gap-batch3:"
                f"{obligation.obligation_id}:{expected_head}"
            ),
            "digest": packet["packet_digest"],
            "category": CATEGORY,
        }
        records.append(packet)

    ids = [row["obligation_id"] for row in records]
    if len(ids) != len(set(ids)):
        raise LearningEvalGapEvidenceError(
            "duplicate covered obligation identity"
        )
    if len(records) != 12:
        raise LearningEvalGapEvidenceError(
            f"expected 12 covered gaps, got {len(records)}"
        )
    volumes = {row["volume_key"] for row in records}
    if len(volumes) != 6:
        raise LearningEvalGapEvidenceError(
            f"expected 6 covered volumes, got {len(volumes)}"
        )

    after = {
        name: _digest_file(path)
        for name, path in canonical_paths.items()
    }
    if before != after:
        raise LearningEvalGapEvidenceError(
            "canonical risk/masterplan sources changed during evidence build"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-learning-eval-gap-evidence-batch3-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "category": CATEGORY,
        "covered_gap_count": len(records),
        "covered_volume_count": len(volumes),
        "already_bound_count": sum(
            1 for row in records if row["binding_present"]
        ),
        "candidate_binding_count": sum(
            1 for row in records if not row["binding_present"]
        ),
        "non_authoritative": True,
        "creates_bindings": False,
        "clears_masterplan_gaps": False,
        "signs_accountability": False,
        "promotes_maturity": False,
        "canonical_source_digests": before,
        "records": records,
    }
    report["report_digest"] = _canonical_digest(report)
    return report


def _canonical_text(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-candidates", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_learning_eval_gap_evidence(
            ROOT,
            expected_head=args.expected_head,
        )
    except LearningEvalGapEvidenceError as exc:
        print(
            f"P1 learning/eval gap evidence: rejected: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_canonical_text(report), encoding="utf-8")

    if args.print_summary:
        print(
            json.dumps(
                {
                    "batch_id": report["batch_id"],
                    "expected_head": report["expected_head"],
                    "covered_gap_count": report["covered_gap_count"],
                    "covered_volume_count": report["covered_volume_count"],
                    "already_bound_count": report["already_bound_count"],
                    "candidate_binding_count": report[
                        "candidate_binding_count"
                    ],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )

    if args.print_candidates:
        print(
            json.dumps(
                [
                    {
                        "volume_key": row["volume_key"],
                        "statement": row["statement"],
                        "obligation_id": row["obligation_id"],
                        "obligation_digest": row["obligation_digest"],
                        "candidate_evidence_ref": row[
                            "candidate_evidence_ref"
                        ],
                    }
                    for row in report["records"]
                ],
                indent=2,
                sort_keys=True,
            )
        )

    print(
        "P1 learning/eval gap evidence: OK "
        f"({report['covered_gap_count']} gaps across "
        f"{report['covered_volume_count']} volumes; "
        f"{report['candidate_binding_count']} binding candidates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
