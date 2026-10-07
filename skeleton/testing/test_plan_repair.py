"""Plan repair tests."""
from __future__ import annotations

from skeleton.intelligence.plan_repair import attempt_plan_repair
from skeleton.organism.quality_state import latest_repair


def test_plan_repair_reports_missing_fields_without_fabrication(tmp_path):
    out = attempt_plan_repair({"era": "", "primary_dps": None, "room_bias": ""}, vision="soulslike arena", root=tmp_path)
    assert out["changed"] == 0
    assert out["ok"] == 0
    assert out["before"] == out["after"]
    assert out["actions"]
    assert out["plan"]["era"] == ""
    assert all(action["applied"] == 0 for action in out["actions"])
    assert latest_repair(root=tmp_path, surface="plan")["kind"] == "repair"
