#!/usr/bin/env python3
"""Independent VOL-001 research-lineage closure verifier.

The verifier intentionally avoids importing the canonical research runtime. It
validates ownership/boundary invariants directly from repository state, checks
AI-tree mirror parity, verifies canonical masterplan bindings, and emits an
exact-head evidence receipt suitable for independent qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]

BOUNDARIES: dict[str, tuple[str, ...]] = {
    "skeleton/research/source_lineage.py": (
        "class ResearchSourceRegistry",
        "class SourceStatus",
        "class CitationRelation",
        "class ReplicationOutcome",
        "def qualification_snapshot",
        "def reconcile_citation_graph",
        "def record_replication",
        "def register_historical_technique",
        "def transition_source_status",
        '"authority_scope": "research-evidence-only"',
    ),
    "skeleton/eval/research_acceptance.py": (
        "class ClaimEvidenceCoverage",
        "class ReproductionEvidence",
        "class ResearchAcceptance",
        "lineage_qualification_digest",
        "def sign_acceptance",
        "def verify_acceptance",
        "high-impact conclusion requires independent review",
        "negative_results_preserved",
    ),
    "skeleton/testing/test_research_lineage.py": (
        "test_research_ingestion_is_content_bound_and_deterministic",
        "test_retraction_propagates_through_cross_source_citation_graph",
        "test_direct_claim_on_retracted_source_is_invalid",
        "test_current_citations_cannot_point_to_non_active_sources",
        "test_metadata_rejects_non_text_object_keys",
    ),
    "skeleton/testing/test_research_system_acceptance.py": (
        "test_complete_independently_reproduced_research_is_eligible",
        "test_uncertainty_omission_blocks_acceptance",
        "test_negative_result_omission_blocks_acceptance",
        "test_high_impact_self_review_rejected",
        "test_research_signoff_invalidates_on_evidence_drift",
        "test_lineage_qualification_is_bound_into_acceptance_identity",
    ),
}

MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "skeleton/research/source_lineage.py",
        "skeleton/ai/research/source_lineage.py",
    ),
)

REQUIRED_VOL001_PATHS = {
    "skeleton/research/source_lineage.py",
    "skeleton/ai/research/source_lineage.py",
    "skeleton/research/__init__.py",
}
REQUIRED_VOL001_TESTS = {
    "skeleton/testing/test_research_lineage.py",
    "skeleton/testing/test_research_system_acceptance.py",
    "tests/test_research_lineage_independent_verifier.py",
}
REQUIRED_VOL001_EVALUATIONS = {
    ".github/workflows/vol001-research-lineage-closure.yml",
    "scripts/verify_research_lineage_closure.py",
}


class VerificationError(RuntimeError):
    """Independent VOL-001 verification failed."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_boundaries(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"research-lineage boundary is missing: {rel}")
            continue
        source = _read_text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost research-lineage token: {token}")
        digests[rel] = _sha256_bytes(source.encode("utf-8"))
    return digests


def _verify_mirrors(root: Path, errors: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        if not source.is_file():
            errors.append(f"canonical research source is missing: {source_rel}")
            continue
        if not mirror.is_file():
            errors.append(f"canonical AI research mirror is missing: {mirror_rel}")
            continue
        try:
            source_bytes = source.read_bytes()
            mirror_bytes = mirror.read_bytes()
        except OSError as exc:
            errors.append(
                f"cannot verify research mirror {source_rel} -> {mirror_rel}: "
                + type(exc).__name__
            )
            continue
        source_digest = _sha256_bytes(source_bytes)
        mirror_digest = _sha256_bytes(mirror_bytes)
        rows.append(
            {
                "source": source_rel,
                "mirror": mirror_rel,
                "source_digest": source_digest,
                "mirror_digest": mirror_digest,
            }
        )
        if source_bytes != mirror_bytes:
            errors.append(
                f"canonical AI research mirror drift: {source_rel} != {mirror_rel}"
            )
    return rows


def _find_volume(master: dict[str, Any], key: str) -> dict[str, Any] | None:
    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        return None
    for row in volumes:
        if isinstance(row, dict) and row.get("key") == key:
            return row
    return None


def _verify_masterplan_binding(root: Path, errors: list[str]) -> dict[str, Any]:
    master = _load_json(root / "machine/ai_master_plan.json")
    volume = _find_volume(master, "VOL-001")
    if volume is None:
        errors.append("machine masterplan is missing VOL-001")
        return {}

    if volume.get("title") != "Scientific & Historical Foundation":
        errors.append("VOL-001 title drifted from canonical authority")
    if volume.get("scope") != "canonical-plan":
        errors.append("VOL-001 scope must remain canonical-plan")
    if volume.get("implementation_status") not in {
        "implemented",
        "hardened",
        "verified",
    }:
        errors.append("VOL-001 implementation status is below implemented")

    implementation_paths = set(volume.get("implementation_paths") or [])
    tests = set(volume.get("tests") or [])
    evaluations = set(volume.get("evaluations") or [])

    missing_paths = sorted(REQUIRED_VOL001_PATHS - implementation_paths)
    missing_tests = sorted(REQUIRED_VOL001_TESTS - tests)
    missing_evaluations = sorted(REQUIRED_VOL001_EVALUATIONS - evaluations)

    if missing_paths:
        errors.append(
            "VOL-001 implementation path binding incomplete: "
            + ", ".join(missing_paths)
        )
    if missing_tests:
        errors.append(
            "VOL-001 test binding incomplete: " + ", ".join(missing_tests)
        )
    if missing_evaluations:
        errors.append(
            "VOL-001 evaluation binding incomplete: "
            + ", ".join(missing_evaluations)
        )

    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    required_phrases = (
        "source, method, result, limitation",
        "failure mode/modern analogue",
        "replication status and negative results",
    )
    for phrase in required_phrases:
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"VOL-001 lost requirement invariant: {phrase}")

    payload = {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "enterprise_grade_state": volume.get("enterprise_grade_state"),
        "enterprise_grade_target": volume.get("enterprise_grade_target"),
        "implementation_paths": sorted(implementation_paths),
        "tests": sorted(tests),
        "evaluations": sorted(evaluations),
        "gaps": list(volume.get("gaps") or []),
    }
    payload["binding_digest"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    boundary_digests = _verify_boundaries(root, errors)
    mirrors = _verify_mirrors(root, errors)
    volume = _verify_masterplan_binding(root, errors)

    head_sha = (
        os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown"
    )
    receipt = {
        "schema_version": 1,
        "verifier": "independent-research-lineage-v1",
        "head_sha": head_sha,
        "volume": "VOL-001",
        "boundary_digests": boundary_digests,
        "mirror_pairs": mirrors,
        "volume_binding": volume,
        "errors": errors,
        "valid": not errors,
    }
    receipt["receipt_digest"] = hashlib.sha256(
        json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
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
            "verifier": "independent-research-lineage-v1",
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "volume": "VOL-001",
            "boundary_digests": {},
            "mirror_pairs": [],
            "volume_binding": {},
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = hashlib.sha256(
            json.dumps(
                receipt,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-001 independent research-lineage closure: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-001 independent research-lineage closure: FAIL")
        for error in receipt["errors"]:
            print(f" - {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
