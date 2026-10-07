"""A missing repair score is not zero, and a missing reason is not unknown."""

import pytest

from skeleton.intelligence.repair_autonomy import repair_effectiveness, run_multi_pass
from skeleton.intelligence.repair_telemetry import capture_telemetry


def test_missing_measurements_are_refused(tmp_path) -> None:
    with pytest.raises(ValueError):
        capture_telemetry("forge", 1, 0, {"ok": False, "reason": "no"}, root=tmp_path)
    with pytest.raises(ValueError):
        capture_telemetry(
            "forge", 1, 0,
            {"ok": False, "before": {"score": 0.2}, "after": {"score": 0.4}},
            root=tmp_path,
        )
    held = capture_telemetry(
        "forge", 1, 0,
        {"ok": "false", "before": {"score": 0.2}, "after": {"score": 0.4}, "reason": "no"},
        root=tmp_path,
    )
    assert held.accepted is False
    assert held.before_score == 0.2

    def repair(**kwargs):
        return {"ok": True, "actions": []}

    with pytest.raises(ValueError):
        run_multi_pass("forge", "demo", repair, root=tmp_path, max_passes=1)
    (tmp_path / "repair_sessions.jsonl").write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        repair_effectiveness(root=tmp_path)
