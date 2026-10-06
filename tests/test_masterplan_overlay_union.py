from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/check_masterplan_overlay_union.py"

def _module():
    spec=importlib.util.spec_from_file_location("overlay_union",SCRIPT)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module

def test_masterplan_overlay_union_is_gapless():
    assert _module().validate() == []

def test_registry_has_all_mandatory_frontier_overlays():
    module=_module()
    import json
    registry=json.loads(module.REGISTRY.read_text(encoding="utf-8"))
    ids={entry["id"] for entry in registry["overlays"]}
    assert ids == {
        "advanced-ai-100","frontier-96","cs-300",
        "learning-400-adversarial-400","psi-1000","ess-1000",
        "competitive-200","game-builder-500",
    }
