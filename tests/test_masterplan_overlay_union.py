from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_masterplan_overlay_union",
    ROOT / "scripts/check_masterplan_overlay_union.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)

def test_masterplan_overlay_union_is_closed():
    assert module.validate() == []

def test_registry_has_expected_frontier_union():
    import json
    data = json.loads((ROOT / "machine/masterplan_overlay_registry.json").read_text())
    assert [row["id"] for row in data["overlays"]] == [
        "frontier-96",
        "advanced-ai-100",
        "cs-300",
        "learning-adversarial-400",
        "psi-1000",
        "ess-1000",
        "competitive-200",
        "game-builder-500",
    ]
