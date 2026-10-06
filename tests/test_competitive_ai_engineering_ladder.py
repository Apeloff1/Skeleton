from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_competitive_ai_engineering_ladder",
    ROOT / "scripts" / "check_competitive_ai_engineering_ladder.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/competitive_ai_engineering_ladder.json",
        "docs/plan/MASTER_PLAN.md",
        "docs/architecture/COMPETITIVE_AI_ENGINEERING_LADDER.md",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root

def _load(root: Path) -> dict:
    return json.loads((root / "machine/competitive_ai_engineering_ladder.json").read_text(encoding="utf-8"))

def _write(root: Path, payload: dict) -> None:
    (root / "machine/competitive_ai_engineering_ladder.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

def test_current_200_level_authority_is_valid() -> None:
    result = MODULE.validate(ROOT)
    assert result == {
        "status": "valid",
        "family_count": 20,
        "stage_count": 10,
        "level_count": 200,
        "first_level": "ENG-001",
        "last_level": "ENG-200",
        "signed_levels": 0,
    }

def test_levels_are_exactly_twenty_by_ten() -> None:
    payload = _load(ROOT)
    assert [row["id"] for row in payload["levels"]] == [f"ENG-{i:03d}" for i in range(1, 201)]
    for family_index in range(20):
        rows = payload["levels"][family_index * 10:(family_index + 1) * 10]
        assert {row["family_id"] for row in rows} == {f"F{family_index + 1:02d}"}
        assert [row["stage"] for row in rows] == list(range(1, 11))

def test_every_level_is_proof_bearing_and_unclaimed() -> None:
    payload = _load(ROOT)
    for row in payload["levels"]:
        assert len(row["implementation_requirements"]) >= 4
        assert len(row["hard_gates"]) >= 6
        assert len(row["adversarial_campaign"]) >= 4
        assert len(row["evidence_required"]) >= 7
        assert len(row["exit_criteria"]) >= 4
        assert row["status"] == "planned"
        assert row["signed"] is False
        assert row["completion_evidence"] == []

def test_rejects_missing_level(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    payload["levels"].pop()
    _write(root, payload)
    with pytest.raises(MODULE.CompetitiveEngineeringError, match="exactly 200 levels"):
        MODULE.validate(root)

def test_rejects_level_reordering(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    payload["levels"][0], payload["levels"][1] = payload["levels"][1], payload["levels"][0]
    _write(root, payload)
    with pytest.raises(MODULE.CompetitiveEngineeringError, match="identity drift"):
        MODULE.validate(root)

def test_rejects_self_signed_level(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    payload["levels"][0]["status"] = "complete"
    payload["levels"][0]["signed"] = True
    payload["levels"][0]["completion_evidence"] = ["trust me"]
    _write(root, payload)
    with pytest.raises(MODULE.CompetitiveEngineeringError, match="may not self-claim completion"):
        MODULE.validate(root)

def test_rejects_security_gate_removal(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    payload["levels"][0]["hard_gates"] = [
        gate for gate in payload["levels"][0]["hard_gates"]
        if "security/privacy/tenant" not in gate
    ]
    _write(root, payload)
    with pytest.raises(MODULE.CompetitiveEngineeringError, match="requires at least 6 entries|missing hard gate"):
        MODULE.validate(root)

def test_final_stage_requires_independent_superiority_authority(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    final = payload["levels"][9]
    final["exit_criteria"] = [
        item.replace("independent superiority authority", "generator")
        for item in final["exit_criteria"]
    ]
    _write(root, payload)
    with pytest.raises(MODULE.CompetitiveEngineeringError, match="independent promotion"):
        MODULE.validate(root)

def test_family_bindings_stay_inside_existing_volume_space() -> None:
    payload = _load(ROOT)
    for family in payload["families"]:
        for ref in family["masterplan_volume_refs"]:
            assert ref.startswith("VOL-")
            assert 0 <= int(ref.split("-")[1]) <= 420
