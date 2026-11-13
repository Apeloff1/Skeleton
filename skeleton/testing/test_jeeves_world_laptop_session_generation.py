"""A diagnostic cannot certify two different persisted player generations."""
from __future__ import annotations

from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def test_diagnostic_rejects_changed_player_save_between_stages(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "player")
    original = flow.acceptance

    def raced(world_id, slot=None):
        result = original(world_id, slot)
        return {
            **result,
            "existing_session": {
                **result["existing_session"],
                "session_digest": "0" * 64,
            },
        }

    monkeypatch.setattr(flow, "acceptance", raced)
    report = flow.diagnose("lighthouse", "player")
    assert report["checks"]["acceptance"] == {
        "ok": False, "error": "laptop_diagnostic_source_changed"
    }
    assert report["next_action"] == "restart_diagnostic_after_source_change"


def test_diagnostic_rejects_nonrestorable_player_save(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "player")
    original = flow.acceptance

    def raced(world_id, slot=None):
        result = original(world_id, slot)
        return {
            **result,
            "existing_session": {**result["existing_session"], "restorable": False},
        }

    monkeypatch.setattr(flow, "acceptance", raced)
    report = flow.diagnose("lighthouse", "player")
    assert report["checks"]["acceptance"]["ok"] is False
    assert report["next_action"] == "restart_diagnostic_after_source_change"


def test_diagnostic_normal_player_save_remains_valid(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "player")
    report = flow.diagnose("lighthouse", "player")
    assert report["checks"]["acceptance"]["ok"] is True
    assert report["checks"]["acceptance"]["persisted_slot_verified"] is True
