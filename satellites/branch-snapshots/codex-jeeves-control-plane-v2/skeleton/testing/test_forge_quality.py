"""Forge quality gates + polish-loop surface tests (Prood forge_quality port)."""
from __future__ import annotations

from skeleton.forge.forge_quality import (
    PRODUCTION_THRESHOLD,
    evaluate,
    evaluate_and_persist,
    fidelity_floor,
    polish_loop,
    summarize,
)
from skeleton.forge.repair import polish_artefact
from skeleton.forge.validators import validate_with_quality
from skeleton.organism.quality_state import latest_quality, load_quality


def _good_item(**overrides):
    base = {
        "id": "artefact-1",
        "grade": 5,
        "stage": "hub",
        "code": "export const behaviour = { tick() {} };\n",
        "skin": {"fidelity": 1.0, "era": "roguelike"},
        "placement": {"region": "overworld"},
        "era": "roguelike",
    }
    base.update(overrides)
    return base


def test_fidelity_floor_rises_with_stage():
    assert fidelity_floor(0) == 0.72
    assert fidelity_floor(5) == 0.82


def test_evaluate_accepts_production_ready_item():
    item = _good_item()
    v = evaluate(
        item,
        stage_index=0,
        stage_floor_grade=0,
        gdd_stages={"hub", "dungeon"},
        regions=["overworld", "dungeon"],
        era="roguelike",
    )
    assert v["passed"] is True
    assert v["production_ready"] is True
    assert v["production_score"] >= PRODUCTION_THRESHOLD
    assert v["failed_gates"] == []


def test_evaluate_rejects_low_grade_and_missing_behaviour():
    item = {
        "grade": 0,
        "stage": "hub",
        "skin": {"fidelity": 0.5},
        "placement": {"region": "nowhere"},
    }
    v = evaluate(
        item,
        stage_index=2,
        stage_floor_grade=1,
        gdd_stages={"hub"},
        regions=["overworld"],
    )
    assert v["passed"] is False
    assert "grade_escalation" in v["failed_gates"]
    assert "fidelity_floor" in v["failed_gates"]
    assert "behaviour_code" in v["failed_gates"]
    assert "placement_valid" in v["failed_gates"]


def test_summarize_batch():
    ok = evaluate(_good_item(), gdd_stages={"hub"}, regions=["overworld"], era="roguelike")
    bad = evaluate({"grade": 0}, stage_floor_grade=1, gdd_stages={"hub"}, regions=["overworld"])
    rollup = summarize([ok, bad])
    assert rollup["count"] == 2
    assert rollup["accepted"] == 1
    assert rollup["rejected"] == 1
    assert "grade_escalation" in rollup["gate_pass_rate"]


def test_persist_quality_writes_quality_log(tmp_path):
    out = evaluate_and_persist(
        _good_item(),
        gdd_stages={"hub"},
        regions=["overworld"],
        era="roguelike",
        artefact_id="artefact-persist",
        root=tmp_path,
    )
    assert out["quality"]["passed"] is True
    row = latest_quality(root=tmp_path, surface="forge", kind="quality")
    assert row
    assert row["metadata"]["kind"] == "forge_quality"
    assert row["metadata"]["artefact_id"] == "artefact-persist"
    assert row["accepted"] is True


def test_polish_loop_repairs_failed_gates_to_production(tmp_path):
    item = {
        "id": "needs-polish",
        "grade": 0,
        "stage": "wrong",
        "skin": {"fidelity": 0.1},
        "placement": {},
    }
    result = polish_loop(
        item,
        stage_index=0,
        stage_floor_grade=0,
        gdd_stages=["hub"],
        regions=["overworld"],
        era="roguelike",
        max_rounds=3,
        persist=True,
        artefact_id="needs-polish",
        root=tmp_path,
        repair_files=None,
    )
    assert result["kind"] == "forge-quality-polish"
    assert result["ok"] == 1
    assert result["production_ready"] is True
    assert result["round_count"] >= 1
    assert result["item"]["grade"] >= 1
    assert result["item"]["placement"]["region"] == "overworld"
    assert result["item"]["stage"] == "hub"
    assert "export const" in result["item"]["code"]
    rows = load_quality(root=tmp_path, surface="forge", kind="quality")
    assert rows


def test_polish_artefact_composes_repair_hook(tmp_path):
    item = {
        "id": "via-repair",
        "grade": 1,
        "stage": "hub",
        "code": "export const behaviour = {};\n",
        "skin": {"fidelity": 0.5, "era": "roguelike"},
        "placement": {"region": "overworld"},
        "era": "roguelike",
    }
    out = polish_artefact(
        item,
        root=tmp_path,
        gdd_stages=["hub"],
        regions=["overworld"],
        era="roguelike",
        artefact_id="via-repair",
        use_file_repair=False,
    )
    assert out["production_ready"] is True
    assert out["persisted"]


def test_validate_with_quality_composes_blueprint_validator():
    bp = {
        "name": "demo",
        "version": "1",
        "systems": [{"id": "core", "depends_on": [], "behaviour": "tick"}],
        "grade": 5,
        "stage": "hub",
        "skin": {"fidelity": 1.0, "era": "soulslike"},
        "placement": {"region": "overworld"},
        "era": "soulslike",
    }
    out = validate_with_quality(
        bp,
        gdd_stages=["hub"],
        regions=["overworld"],
        era="soulslike",
    )
    assert out["kind"] == "blueprint-quality-verdict"
    assert out["validation"]["valid"] is True
    assert out["quality"]["passed"] is True
    assert out["valid"] is True


def test_validate_with_quality_flags_structural_and_quality():
    bp = {"name": "broken", "version": "1", "systems": []}  # empty systems → invalid
    out = validate_with_quality(bp, gdd_stages=["hub"], regions=["overworld"])
    assert out["validation"]["valid"] is False
    assert out["valid"] is False
