from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.verify_verification_evidence_closure import (
    BOUNDARIES,
    MIRROR_PAIRS,
    verify_repository,
)


ROOT = Path(__file__).resolve().parents[1]


def _copy_fixture(tmp_path: Path) -> None:
    required = set(BOUNDARIES)
    required.update(
        {
            "machine/ai_app_construction.json",
            "machine/ai_implementation_handoff.json",
            "machine/ai_closure_evidence.json",
        }
    )
    for source_rel, mirror_rel in MIRROR_PAIRS:
        required.add(source_rel)
        required.add(mirror_rel)
    for relative in sorted(required):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def test_repository_verification_evidence_independent_verifier_is_green(
    monkeypatch,
) -> None:
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "exact-head-test")

    receipt = verify_repository(ROOT)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["verifier"] == "independent-verification-evidence-v1"
    assert receipt["head_sha"] == "exact-head-test"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert receipt["handoff_digest"]


def test_verification_evidence_verifier_detects_runtime_mirror_drift(
    tmp_path: Path,
) -> None:
    _copy_fixture(tmp_path)
    mirror = tmp_path / MIRROR_PAIRS[-1][1]
    mirror.write_text(
        mirror.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    receipt = verify_repository(tmp_path)

    assert receipt["valid"] is False
    assert any(
        "canonical AI mirror drift" in item
        for item in receipt["errors"]
    )


def test_verification_evidence_verifier_rejects_false_closed_state(
    tmp_path: Path,
) -> None:
    _copy_fixture(tmp_path)
    construction_path = tmp_path / "machine/ai_app_construction.json"
    construction = json.loads(
        construction_path.read_text(encoding="utf-8")
    )
    gap = next(
        item
        for item in construction["gap_register"]
        if item["id"] == "gap-verification-evidence-contract"
    )
    gap["status"] = "closed"
    construction_path.write_text(
        json.dumps(construction, indent=2) + "\n",
        encoding="utf-8",
    )

    receipt = verify_repository(tmp_path)

    assert receipt["valid"] is False
    assert any(
        "closed verification gap requires closed" in item
        for item in receipt["errors"]
    )


def test_verification_evidence_verifier_detects_dependency_drift(
    tmp_path: Path,
) -> None:
    _copy_fixture(tmp_path)
    handoff_path = tmp_path / "machine/ai_implementation_handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in handoff["entries"]
        if item["gap"] == "gap-verification-evidence-contract"
    )
    entry["depends_on"] = ["gap-invented"]
    handoff_path.write_text(
        json.dumps(handoff, indent=2) + "\n",
        encoding="utf-8",
    )

    receipt = verify_repository(tmp_path)

    assert receipt["valid"] is False
    assert any(
        "verification dependency graph mismatch" in item
        for item in receipt["errors"]
    )
