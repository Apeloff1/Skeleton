#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-006 model-development boundaries.

This verifier intentionally does not import the modeling runtime. It binds the
canonical plan to byte-identical source/AI mirrors and independently inspects
lineage, governance, bounded training, evaluation, and publication boundaries.
Behavioral execution remains a separate workflow job.
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
PAIRS = (
    (Path("skeleton/modeling/registry.py"), Path("skeleton/ai/modeling/registry.py")),
    (Path("skeleton/modeling/training.py"), Path("skeleton/ai/modeling/training.py")),
    (Path("skeleton/modeling/evaluation.py"), Path("skeleton/ai/modeling/evaluation.py")),
    (Path("skeleton/modeling/publication.py"), Path("skeleton/ai/modeling/publication.py")),
)
QUALIFICATION_GAP = (
    "independent model-development reproducibility, registry, evaluation, "
    "and publication verification remains pending"
)
REQUIRED_PATHS = {
    "skeleton/modeling/registry.py",
    "skeleton/modeling/training.py",
    "skeleton/modeling/evaluation.py",
    "skeleton/modeling/publication.py",
}
REQUIRED_TESTS = {
    "skeleton/testing/test_vol006_model_registry.py",
    "skeleton/testing/test_vol006_training_execution.py",
    "skeleton/testing/test_vol006_artifact_publication.py",
    "skeleton/testing/test_vol006_evaluation_eligibility.py",
}
REQUIRED_CONTRACTS = {
    "DatasetManifest",
    "TrainingRun",
    "ModelArtifact",
    "TrainingLineage",
}

TOKENS = {
    "registry.py": (
        "class DatasetManifest",
        "content_digest",
        "rights",
        "pii_policy",
        "dedup_digest",
        "contamination_digest",
        '"owned","licensed","public-domain","research-restricted"',
        '"none","redacted","consented","restricted"',
        "class TrainingRun",
        "code_digest",
        "config_digest",
        "hardware_digest",
        "seed",
        "class ModelArtifact",
        'authority_scope:str="research-only"',
        "registry cannot grant production authority",
        "class TrainingLineage",
        "Append-only bounded evidence registry. No method promotes a model.",
        "unknown dataset lineage",
        "artifact requires completed run",
    ),
    "training.py": (
        "MAX_STEPS=10_000_000",
        "MAX_CHECKPOINTS=1024",
        "class TrainingBudget",
        "class StepReceipt",
        "class TrainingCheckpoint",
        "class TrainingExecution",
        "training budget exceeded",
        "checkpoint budget exceeded",
        "checkpoint receipt chain mismatch",
        "checkpoint state mismatch",
        '"authority_scope":"research-only"',
    ),
    "evaluation.py": (
        "class EvaluationEvidence",
        'authority_scope:str="evidence-only"',
        "evaluation cannot grant execution authority",
        "class PromotionEligibility",
        'authority_scope:str="eligibility-only"',
        "eligibility cannot grant execution authority",
        "def assess_eligibility",
        "evaluation artifact mismatch",
        "evaluation completion mismatch",
        "artifact completion lineage mismatch",
        "evaluation suite mismatch",
    ),
    "publication.py": (
        "class TrainingCompletion",
        'authority_scope:str="research-only"',
        "completion cannot grant production authority",
        "class ArtifactPublisher",
        "All checks precede registry mutation",
        "completion run mismatch",
        "completion seed mismatch",
        "artifact run mismatch",
        "completion already bound to different artifact",
    ),
}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _verify_volume(master: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    rows = master.get("volumes")
    volume = next(
        (
            row for row in rows
            if isinstance(row, dict) and row.get("key") == "VOL-006"
        ),
        None,
    ) if isinstance(rows, list) else None
    if not isinstance(volume, dict):
        errors.append("masterplan missing VOL-006")
        return {}

    if volume.get("title") != "Model Development Program":
        errors.append("VOL-006 title drift")
    if volume.get("scope") != "canonical-plan":
        errors.append("VOL-006 scope drift")
    if volume.get("implementation_status") not in {"implemented", "hardened", "verified"}:
        errors.append("VOL-006 implementation status below implemented")

    paths = set(volume.get("implementation_paths") or [])
    tests = set(volume.get("tests") or [])
    contracts = set(volume.get("contracts") or [])
    for label, required, actual in (
        ("implementation path", REQUIRED_PATHS, paths),
        ("test", REQUIRED_TESTS, tests),
        ("contract", REQUIRED_CONTRACTS, contracts),
    ):
        missing = sorted(required - actual)
        if missing:
            errors.append(
                f"VOL-006 {label} binding incomplete: {', '.join(missing)}"
            )

    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    for phrase in (
        "rights, integrity, deduplication, contamination and PII metadata",
        "exact data/code/config/hardware/evaluation lineage",
        "isolated from production promotion authority",
    ):
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"VOL-006 requirement invariant lost: {phrase}")

    gaps = list(volume.get("gaps") or [])
    if gaps not in ([QUALIFICATION_GAP], []):
        errors.append(
            "VOL-006 gap state must be pending independent qualification or signed"
        )
    if not gaps and volume.get("completion_checkbox") is not True:
        errors.append("VOL-006 cannot clear qualification gap before signoff")
    if gaps and volume.get("completion_checkbox") is True:
        errors.append("VOL-006 cannot remain signed with pending qualification")

    binding = {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "completion_checkbox_mark": volume.get("completion_checkbox_mark"),
        "gaps": gaps,
        "implementation_paths": sorted(paths),
        "tests": sorted(tests),
        "contracts": sorted(contracts),
    }
    binding["binding_digest"] = _digest_json(binding)
    return binding


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    binding = _verify_volume(master, errors)

    source_digests: dict[str, str] = {}
    mirror_digests: dict[str, str] = {}
    inspected = 0
    for canonical_rel, mirror_rel in PAIRS:
        canonical = root / canonical_rel
        mirror = root / mirror_rel
        try:
            canonical_bytes = canonical.read_bytes()
            mirror_bytes = mirror.read_bytes()
        except OSError as exc:
            errors.append(
                f"cannot read model-development source pair "
                f"{canonical_rel.name}: {type(exc).__name__}"
            )
            continue
        source_digests[canonical_rel.as_posix()] = _sha(canonical_bytes)
        mirror_digests[mirror_rel.as_posix()] = _sha(mirror_bytes)
        if canonical_bytes != mirror_bytes:
            errors.append(
                f"VOL-006 source/AI mirror drift: {canonical_rel.name}"
            )
        source = canonical_bytes.decode("utf-8")
        for token in TOKENS[canonical_rel.name]:
            inspected += 1
            if token not in source:
                errors.append(
                    f"VOL-006 invariant missing from "
                    f"{canonical_rel.name}: {token}"
                )

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol006-model-development-v1",
        "volume": "VOL-006",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "source_digests": source_digests,
        "mirror_digests": mirror_digests,
        "checked_invariant_count": inspected,
        "volume_binding": binding,
        "errors": errors,
        "valid": not errors,
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
            "verifier": "independent-vol006-model-development-v1",
            "volume": "VOL-006",
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
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-006 independent model-development verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-006 independent model-development verification: FAIL")
        for error in receipt["errors"]:
            print(f" - {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
