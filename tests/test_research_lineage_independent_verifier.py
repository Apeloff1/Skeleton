from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_research_lineage_closure import (
    BOUNDARIES,
    MIRROR_PAIRS,
    REQUIRED_VOL001_EVALUATIONS,
    REQUIRED_VOL001_PATHS,
    REQUIRED_VOL001_TESTS,
    verify_repository,
)


def _write_masterplan(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    payload = {
        "volumes": [
            {
                "key": "VOL-001",
                "title": "Scientific & Historical Foundation",
                "scope": "canonical-plan",
                "implementation_status": "implemented",
                "requirements": [
                    "Preserve scientific claims with source, method, result, limitation and correction/retraction lineage.",
                    "Track historical techniques by problem/mechanism/failure mode/modern analogue instead of citation popularity.",
                    "Separate replication status and negative results from narrative confidence.",
                ],
                "implementation_paths": sorted(REQUIRED_VOL001_PATHS),
                "tests": sorted(REQUIRED_VOL001_TESTS),
                "evaluations": sorted(REQUIRED_VOL001_EVALUATIONS),
                "gaps": [
                    "independent exact-head AI Research Lineage Closure qualification remains pending"
                ],
                "completion_checkbox": False,
                "enterprise_grade_state": "designed",
                "enterprise_grade_target": "enterprise_qualified",
            }
        ]
    }
    (machine / "ai_master_plan.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"# {token}" for token in tokens) + "\n",
            encoding="utf-8",
        )
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(source.read_bytes())
    _write_masterplan(root)
    return root


def test_independent_research_verifier_accepts_complete_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "research-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "research-head"
    assert receipt["volume"] == "VOL-001"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert len(receipt["receipt_digest"]) == 64


def test_independent_research_verifier_rejects_boundary_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    source = root / "skeleton" / "research" / "source_lineage.py"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "# def qualification_snapshot\n",
            "",
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "lost research-lineage token: def qualification_snapshot" in error
        for error in receipt["errors"]
    )


def test_independent_research_verifier_rejects_ai_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = root / "skeleton" / "ai" / "research" / "source_lineage.py"
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "canonical AI research mirror drift" in error
        for error in receipt["errors"]
    )


def test_independent_research_verifier_rejects_masterplan_path_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["implementation_paths"].remove(
        "skeleton/research/source_lineage.py"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "VOL-001 implementation path binding incomplete" in error
        for error in receipt["errors"]
    )


def test_independent_research_verifier_rejects_missing_closure_evaluation(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["evaluations"].remove(
        ".github/workflows/vol001-research-lineage-closure.yml"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "VOL-001 evaluation binding incomplete" in error
        for error in receipt["errors"]
    )


def test_independent_research_verifier_rejects_requirement_erosion(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["requirements"] = [
        "Preserve research somehow."
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("VOL-001 lost requirement invariant" in error for error in receipt["errors"])


def test_independent_research_verifier_rejects_acceptance_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = root / "skeleton" / "ai" / "evaluation" / "research_acceptance.py"
    mirror.write_text("# acceptance drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "canonical AI research mirror drift" in error
        and "research_acceptance.py" in error
        for error in receipt["errors"]
    )
