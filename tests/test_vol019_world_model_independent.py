from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.verify_vol019_world_model import verify_repository


ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/ai_master_plan.json",
        "skeleton/simulation/environment.py",
        "skeleton/simulation/world_model.py",
        "skeleton/simulation/scenario_runtime.py",
        "skeleton/ai/simulation/environment.py",
        "skeleton/ai/simulation/world_model.py",
        "skeleton/ai/simulation/scenario_runtime.py",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def test_independent_vol019_accepts_current_implementation(tmp_path: Path, monkeypatch) -> None:
    root = _fixture(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "vol019-head")
    receipt = verify_repository(root)
    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "vol019-head"
    assert receipt["volume"] == "VOL-019"
    assert receipt["checked_invariant_count"] >= 20
    assert len(receipt["source_digests"]) == 3
    assert len(receipt["mirror_digests"]) == 3
    assert len(receipt["volume_binding"]["binding_digest"]) == 64
    assert len(receipt["receipt_digest"]) == 64


def test_independent_vol019_rejects_source_mirror_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    mirror = root / "skeleton/ai/simulation/world_model.py"
    mirror.write_text(mirror.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "VOL-019 source/AI mirror drift: world_model.py" in receipt["errors"]


def test_independent_vol019_rejects_real_postcondition_boundary_removal(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/simulation/world_model.py",
        "skeleton/ai/simulation/world_model.py",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "simulation result cannot satisfy a real-world postcondition",
            "simulation result boundary removed",
        )
        path.write_text(text, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "simulation result cannot satisfy a real-world postcondition" in error
        for error in receipt["errors"]
    )


def test_independent_vol019_rejects_simulation_effect_scope_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/simulation/scenario_runtime.py",
        "skeleton/ai/simulation/scenario_runtime.py",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            'effect_scope: str = "simulation_only"',
            'effect_scope: str = "real_effect"',
        )
        path.write_text(text, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("effect_scope" in error for error in receipt["errors"])


def test_independent_vol019_rejects_missing_plan_binding(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    volume = next(row for row in data["volumes"] if row["key"] == "VOL-019")
    volume["implementation_paths"].remove("skeleton/simulation/world_model.py")
    path.write_text(json.dumps(data), encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("implementation binding incomplete" in error for error in receipt["errors"])


def test_independent_vol019_rejects_uncertainty_monotonicity_boundary_removal(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/simulation/world_model.py",
        "skeleton/ai/simulation/world_model.py",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "uncertainty propagation must be monotonic",
            "uncertainty may regress",
        )
        path.write_text(text, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("uncertainty propagation must be monotonic" in error for error in receipt["errors"])
