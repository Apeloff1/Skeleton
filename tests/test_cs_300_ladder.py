from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "machine" / "cs_300_computer_science_ladder.json"
MODULE = ROOT / "scripts" / "check_cs_300_ladder.py"

def _load_validator():
    spec = importlib.util.spec_from_file_location("check_cs_300_ladder", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_cs_300_contract_is_valid():
    module = _load_validator()
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert module.validate(data) == []

def test_cs_300_has_exact_identity_space():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert [x["id"] for x in data["layers"]] == [f"CS300-{i:03d}" for i in range(1, 301)]
    assert len(data["strata"]) == 30
    assert len(data["construction_waves"]) == 30

def test_cs_300_does_not_break_volume_freeze():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert data["scope"]["expands_top_level_volumes"] is False
    assert data["scope"]["frozen_volume_range"] == ["VOL-000", "VOL-420"]
    assert data["scope"]["relationship_to_frontier_96"] == "strictly-above"

def test_cs_300_completion_reflects_current_layer_receipts():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    completed = [layer for layer in data["layers"] if layer["complete"] is True]
    assert data["completion"]["signed_complete"] == len(completed)
    assert data["completion"]["cs_300_qualified"] is (len(completed) == 300)
    assert all(
        layer["maturity"] == "signed_complete"
        and layer["implementation_signed"] is True
        and layer["independent_verification_signed"] is True
        and layer["evidence"]
        for layer in completed
    )
    if data["completion"]["cs_300_qualified"]:
        assert data["layers"][-1]["independent_verification_signed"] is True


def test_cs_300_validator_rejects_unbacked_completion_claims():
    module = _load_validator()
    data = json.loads(DATA.read_text(encoding="utf-8"))
    layer = next(x for x in data["layers"] if x["complete"])
    layer["independent_verification_signed"] = False
    assert any("without independent verification signature" in error
               for error in module.validate(data))

def test_each_layer_has_contract_proof_owner_and_dependency_discipline():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    ids = {x["id"] for x in data["layers"]}
    for layer in data["layers"]:
        assert layer["build_contract"]
        assert layer["acceptance_proof"]
        assert layer["owner_work_packages"]
        assert layer["entry_gate"] == "frontier-96-qualified"
        assert all(dep in ids for dep in layer["depends_on"])
