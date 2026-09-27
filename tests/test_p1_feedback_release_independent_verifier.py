from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_p1_feedback_release_closure import (
    EXPECTED_GAPS,
    SURFACES,
    verify_repository,
)


def _valid_repo(root: Path) -> Path:
    for rel, tokens in SURFACES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"# {token}" for token in tokens) + "\n",
            encoding="utf-8",
        )

    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    (machine / "ai_app_construction.json").write_text(
        json.dumps(
            {
                "gap_register": [
                    {
                        "id": gap_id,
                        "plane": plane,
                        "status": "closed",
                    }
                    for gap_id, plane in EXPECTED_GAPS.items()
                ]
            }
        ),
        encoding="utf-8",
    )
    return root


def test_independent_p1_verifier_accepts_complete_surfaces(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "p1-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "p1-head"
    assert len(receipt["surface_digests"]) == len(SURFACES)
    assert set(receipt["gap_state"]) == set(EXPECTED_GAPS)


def test_independent_p1_verifier_rejects_feedback_holdout_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "skeleton/learning/promotion.py"
    path.write_text("# class ExperimentSpec\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "holdout feedback cannot enter promotion evaluation" in error
        for error in receipt["errors"]
    )


def test_independent_p1_verifier_rejects_release_override_guard_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "skeleton/release/slo_promotion.py"
    source = path.read_text(encoding="utf-8")
    path.write_text(
        source.replace(
            "# operator override cannot promote failed SLO evidence\n",
            "",
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "operator override cannot promote failed SLO evidence" in error
        for error in receipt["errors"]
    )


def test_independent_p1_verifier_rejects_masterplan_plane_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["plane"] = "wrong-plane"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("masterplan plane drift" in error for error in receipt["errors"])

def test_independent_p1_verifier_rejects_reopened_gap(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "must remain closed" in error
        for error in receipt["errors"]
    )
