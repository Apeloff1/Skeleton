from __future__ import annotations

import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "machine" / "frontier_96_ai_ladder.json"
MODULE = ROOT / "scripts" / "check_frontier_96_ladder.py"

def _validator():
    ns = runpy.run_path(str(MODULE))
    return ns["validate"]

def test_frontier_96_contract_is_valid():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert _validator()(data) == []

def test_frontier_96_has_exact_identity_space():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert [x["id"] for x in data["layers"]] == [f"F96-{i:03d}" for i in range(1, 97)]
    assert len(data["strata"]) == 12
    assert all(len([x for x in data["layers"] if x["stratum_id"] == s["id"]]) == 8 for s in data["strata"])

def test_frontier_96_does_not_break_volume_freeze():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert data["scope"]["expands_top_level_volumes"] is False
    assert data["scope"]["frozen_volume_range"] == ["VOL-000", "VOL-420"]
    assert all(not layer["id"].startswith("VOL-") for layer in data["layers"])

def test_frontier_96_starts_unsigned():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert data["completion"]["signed_complete"] == 0
    assert data["completion"]["frontier_96_qualified"] is False
    assert all(layer["complete"] is False for layer in data["layers"])
