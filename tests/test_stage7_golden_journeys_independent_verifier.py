from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.verify_stage7_golden_journeys import (
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


def test_stage7_independent_verifier_is_green(monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "stage7-exact-head")
    receipt = verify_repository(ROOT)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["verifier"] == "independent-stage7-golden-journeys-v1"
    assert receipt["head_sha"] == "stage7-exact-head"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert receipt["machine_digest"]


def test_stage7_verifier_detects_missing_browser_journey_token(
    tmp_path: Path,
) -> None:
    _copy_fixture(tmp_path)
    target = tmp_path / "frontend/scripts/test-operation-stream-session.mjs"
    source = target.read_text(encoding="utf-8")
    target.write_text(
        source.replace(
            "slow browser recovers from compacted replay gap through authoritative floor",
            "removed slow browser journey",
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(tmp_path)

    assert receipt["valid"] is False
    assert any(
        "lost Stage-7 token" in error
        and "slow browser" in error
        for error in receipt["errors"]
    )


def test_stage7_verifier_detects_engine_service_mirror_drift(
    tmp_path: Path,
) -> None:
    _copy_fixture(tmp_path)
    mirror = tmp_path / MIRROR_PAIRS[0][1]
    mirror.write_text(
        mirror.read_text(encoding="utf-8") + "\n# mirror drift\n",
        encoding="utf-8",
    )

    receipt = verify_repository(tmp_path)

    assert receipt["valid"] is False
    assert any(
        "canonical AI mirror drift" in error
        for error in receipt["errors"]
    )


def test_stage7_verifier_rejects_false_closure_with_open_dependencies(
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
        if item["id"] == "gap-e2e-golden-journeys"
    )
    gap["status"] = "closed"
    construction_path.write_text(
        json.dumps(construction, indent=2) + "\n",
        encoding="utf-8",
    )

    receipt = verify_repository(tmp_path)

    assert receipt["valid"] is False
    assert any(
        "closed Stage-7 gap has non-closed dependencies" in error
        for error in receipt["errors"]
    )


def test_stage7_verifier_detects_dependency_drift(tmp_path: Path) -> None:
    _copy_fixture(tmp_path)
    handoff_path = tmp_path / "machine/ai_implementation_handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in handoff["entries"]
        if item["gap"] == "gap-e2e-golden-journeys"
    )
    entry["depends_on"] = ["gap-invented"]
    handoff_path.write_text(
        json.dumps(handoff, indent=2) + "\n",
        encoding="utf-8",
    )

    receipt = verify_repository(tmp_path)

    assert receipt["valid"] is False
    assert any(
        "Stage-7 dependency graph mismatch" in error
        for error in receipt["errors"]
    )
