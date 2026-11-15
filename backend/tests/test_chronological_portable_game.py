"""July workflow recovery — exact portable artifact and replay regressions."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from gameforge.workflow import internal_build_system as builds
from gameforge.workflow.portable_runtime import Session, campaign_from_game_data, smoke


def game():
    return {"levels": {"one": {"name": "Cavern", "difficulty": .2},
                       "two": {"name": "Citadel", "difficulty": 1}},
            "systems": {"combat": {"enabled": True}, "network": {}},
            "narrative": {"premise": "Find the relic"}}


def test_real_campaign_and_replay():
    campaign = campaign_from_game_data("Relic", game())
    session = Session(campaign)
    with pytest.raises(ValueError):
        session.action("advance")
    s = session.state
    while session.state.enemy_hp:
        session.action("attack")
    assert session.state.gold > s.gold
    assert session.state.xp > s.xp
    with pytest.raises(ValueError):
        session.action("advance")
    session.action("explore")
    session.action("advance")
    assert session.state.stage == 1
    receipt = session.receipt()
    assert Session.replay(campaign, receipt).state == session.state
    with pytest.raises(ValueError):
        Session.replay(campaign, {**receipt, "head": "0"*64})
    assert smoke(campaign)["stages"] == 2


def test_full_size_campaign_smokes_and_replays():
    large = {"levels": {str(i): {"difficulty": 1} for i in range(128)}}
    proof = smoke(campaign_from_game_data("Stress", large))
    assert proof["outcome"] == "victory" and proof["stages"] == 128
    assert proof["replay_verified"]


def test_build_is_reproducible_and_contains_playable_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(builds, "require_execution_allowed", lambda *_: True)
    first = builds.InternalBuildSystem("Relic").build_game(game())
    second = builds.InternalBuildSystem("Relic").build_game(game())
    assert first["bundle_bytes"] == second["bundle_bytes"]
    assert first["qualification"]["replay_verified"]
    assert first["release_qualified"] is False
    assert first["signature"]["signed"] is False
    assert first["signature"]["digest"] == hashlib.sha256(first["bundle_bytes"]).hexdigest()
    with zipfile.ZipFile(io.BytesIO(first["bundle_bytes"])) as archive:
        assert archive.testzip() is None
        assert "campaign.json" in archive.namelist()
        # Files are generated from a fixed inventory, not caller-controlled paths.
        archive.extractall(tmp_path)
    from gameforge.workflow.portable_runtime import load_campaign
    campaign = load_campaign(tmp_path / "game_manifest.json")
    assert smoke(campaign) == json.loads((tmp_path / "reference_smoke.json").read_text())
    content = json.loads((tmp_path / "campaign.json").read_text())
    content["levels"][0]["enemy_hp"] += 1
    (tmp_path / "campaign.json").write_text(json.dumps(content))
    with pytest.raises(ValueError, match="digest"):
        load_campaign(tmp_path / "game_manifest.json")


@pytest.mark.parametrize("difficulty", [float("nan"), float("inf"), True, -1, 2, "hard"])
def test_invalid_game_data_fails_closed(difficulty):
    with pytest.raises(ValueError):
        campaign_from_game_data("Bad", {"levels": {"x": {"difficulty": difficulty}}})


def test_execution_guard_precedes_packaging(monkeypatch):
    monkeypatch.setattr(builds, "require_execution_allowed", lambda *_: False)
    assert builds.InternalBuildSystem("Relic").build_game(game())["disabled"]
