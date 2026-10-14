from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_competitive_ai_benchmark_governance",
    ROOT / "scripts" / "check_competitive_ai_benchmark_governance.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/competitive_ai_benchmark_governance.json",
        "machine/competitive_ai_engineering_ladder.json",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root

def _load(root: Path) -> dict:
    return json.loads((root / "machine/competitive_ai_benchmark_governance.json").read_text())

def _write(root: Path, payload: dict) -> None:
    (root / "machine/competitive_ai_benchmark_governance.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

def test_current_benchmark_governance_is_valid() -> None:
    result = MODULE.validate(ROOT)
    assert result["status"] == "valid"
    assert result["preregistration_fields"] >= 18
    assert result["anti_gaming_rules"] >= 8
    assert result["promotion_states"] == 9
    assert result["cross_family_journeys"] == 8
    assert result["covered_families"] >= 18

def test_rejects_optional_preregistration(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    payload["preregistration"]["required"] = False
    _write(root, payload)
    with pytest.raises(MODULE.BenchmarkGovernanceError, match="preregistration"):
        MODULE.validate(root)

def test_rejects_missing_independent_verifier(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    payload["preregistration"]["required_fields"].remove("independent_verifier_identity")
    _write(root, payload)
    with pytest.raises(MODULE.BenchmarkGovernanceError, match="independent_verifier_identity"):
        MODULE.validate(root)

def test_rejects_cross_family_journey_loss(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    payload["cross_family_journeys"].pop()
    _write(root, payload)
    with pytest.raises(MODULE.BenchmarkGovernanceError, match="exactly 8"):
        MODULE.validate(root)

def test_rejects_unknown_family_binding(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    payload = _load(root)
    payload["cross_family_journeys"][0]["families"][0] = "F99"
    _write(root, payload)
    with pytest.raises(MODULE.BenchmarkGovernanceError, match="unknown family"):
        MODULE.validate(root)
