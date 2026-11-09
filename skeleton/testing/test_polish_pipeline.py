"""Polish pipeline orchestration tests (evaluate → improve → repair → scorecard)."""
from __future__ import annotations

import pytest

from skeleton.forge.polish_pipeline import (
    batch_polish,
    inspect_artefact,
    one_shot_improve,
    pipeline_from_polish_artefact,
    qc_dashboard,
    repair_cta_payload,
    run_polish,
)
from skeleton.organism.quality_state import latest_quality


def _item(**overrides):
    base = {
        "id": "blade",
        "grade": 1,
        "stage": "hub",
        "code": "export const behaviour = { tick() {} };\n",
        "skin": {"fidelity": 0.4, "era": "roguelike"},
        "placement": {"region": "void"},
        "era": "roguelike",
    }
    base.update(overrides)
    return base


CTX = {"gdd_stages": {"hub"}, "regions": ["overworld"]}


def test_inspect_empty_returns_placeholder():
    out = inspect_artefact(None)
    assert out["ok"] == 0
    assert out["scorecard"]["empty"] is True


def test_inspect_is_read_only():
    item = _item()
    out = inspect_artefact(item, **CTX)
    assert out["ok"] == 0
    assert "fidelity_floor" in out["scorecard"]["failed_gates"]
    assert item["skin"]["fidelity"] == 0.4


def test_run_polish_reaches_production_and_persists(tmp_path):
    item = _item()
    out = run_polish(item, root=tmp_path, use_file_repair=False, artefact_id="blade", **CTX)
    assert out["ok"] == 1 and out["production_ready"] is True
    assert out["before"]["production_ready"] is False
    assert out["after"]["production_ready"] is True
    assert set(out["delta"]["gates_cleared"]) >= {"fidelity_floor", "placement_valid"}
    assert out["delta"]["improved"] is True
    assert out["after"]["round_count"] == out["progress"]["round_count"] >= 1
    assert out["progress"]["steps"][-1]["status"] == "ready"
    # Input is not mutated; polished copy carries the fixes.
    assert item["placement"]["region"] == "void"
    assert out["item"]["placement"]["region"] == "overworld"
    row = latest_quality(root=tmp_path, surface="forge", kind="quality")
    assert row and row["metadata"]["artefact_id"] == "blade"


def test_run_polish_uses_supplied_file_repair():
    calls = []

    def fake_repair(files, *, request="", root=None):
        calls.append(request)
        return {"ok": 1, "files": {**files, "fixed.gd": "extends Node\n"}, "actions": [{"path": "fixed.gd"}]}

    item = _item(files={"main.gd": "extends Node\nfunc _ready():\n\tpass\n"})
    out = run_polish(item, persist=False, repair_files=fake_repair, max_rounds=1, **CTX)
    assert calls == ["forge-quality polish round 1"]
    assert "fixed.gd" in out["item"]["files"]
    gates = [a["gate"] for a in out["progress"]["steps"][0]["actions"]]
    assert "file_repair" in gates


def test_run_polish_rejects_bad_rounds():
    with pytest.raises(ValueError):
        run_polish(_item(), persist=False, use_file_repair=False, max_rounds=0)


def test_one_shot_improve_single_pass():
    out = one_shot_improve(_item(), **CTX)
    assert out["before"]["passed"] is False
    assert out["after"]["passed"] is True
    assert {a["gate"] for a in out["actions"]} >= {"fidelity_floor", "placement_valid"}
    assert out["scorecard"]["passed"] is True


def test_batch_polish_rollup():
    items = [_item(id="a"), _item(id="b", code="", systems=[])]
    out = batch_polish(items, **CTX)
    assert out["count"] == 2
    assert out["production_ready_count"] == out["batch_scorecard"]["production_ready_count"]
    assert out["ok"] == int(out["production_ready_count"] == 2)


def test_qc_dashboard_dedupes_ctas_and_includes_phase_ladder():
    items = [_item(id="a"), _item(id="b")]
    out = qc_dashboard(items, manifest={"era": "roguelike"}, assets={"forged": 0}, **CTX)
    gates = [c["gate"] for c in out["repair_ctas"]]
    assert len(gates) == len(set(gates))
    assert out["repair_ctas"][0]["artefact_id"] == "a"
    assert out["summary"]["blocked"] == 2
    assert out["phase_gates"]["kind"] == "phase-gate-scorecard"
    assert out["summary"]["phase_all_green"] is False
    assert qc_dashboard(items, **CTX)["phase_gates"] is None


def test_repair_cta_payload_states():
    blocked = repair_cta_payload(_item(), **CTX)
    assert blocked["enabled"] is True
    assert blocked["primary_action"]["gate"] == "fidelity_floor"
    good = _item(grade=5, skin={"fidelity": 1.0, "era": "roguelike"}, placement={"region": "overworld"})
    ready = repair_cta_payload(good, **CTX)
    assert ready["enabled"] is False and ready["label"] == "Production ready"


def test_pipeline_from_polish_artefact_bridge(tmp_path):
    out = pipeline_from_polish_artefact(_item(), root=tmp_path, use_file_repair=False, artefact_id="blade", **CTX)
    assert out["production_ready"] is True
    assert out["after"]["round_count"] >= 1
    assert out["progress"]["steps"]
