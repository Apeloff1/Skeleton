"""Campaign acceptance: source custody, deterministic transitions, retries and exports."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import pytest

from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.campaign import (
    CampaignError, open_campaign, parse_campaign, verify_campaign,
    step_campaign, retry_campaign, export_campaign, verify_export,
)
from skeleton.game.gameplay.ridge_rescue.custody import digest
from skeleton.game.gameplay.ridge_rescue.engine import available_actions
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.campaign_cli import main

SOURCE = Path(__file__).parents[1] / "game" / "gameplay" / "ridge_rescue" / "cinder_ridge_campaign.json"


def _source():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _play_first():
    session = open_campaign(_source())
    for action in acceptance_actions("protect"):
        session = step_campaign(session, action, expected_head=session["head"])
    return session


def test_first_chapter_earned_and_next_world_activated():
    session = _play_first()
    result = verify_campaign(session)
    assert result["index"] == 1
    assert result["status"] == "playing"
    assert result["session"]["completed"][0]["state"]["status"] == "won:protect"
    assert result["session"]["active"]["world"]["name"] == "Cinder Ridge - Last Signal"
    assert result["session"]["active"]["state"]["turn"] == 0


def test_replay_and_export_round_trip():
    session = _play_first()
    export = export_campaign(session)
    assert verify_export(json.dumps(export).encode())["head"] == session["head"]
    assert verify_campaign(json.dumps(session))["index"] == 1


def test_stale_head_and_invalid_action_do_not_mutate():
    session = open_campaign(_source())
    before = deepcopy(session)
    with pytest.raises(CampaignError, match="stale"):
        step_campaign(session, {"verb": "rest"}, expected_head="0" * 64)
    with pytest.raises(CampaignError, match="unavailable"):
        step_campaign(session, {"verb": "rescue", "target": "nonexistent"}, expected_head=session["head"])
    assert session == before


def test_source_replacement_rejected_even_with_new_head():
    session = _play_first()
    forged = deepcopy(session)
    forged["campaign"]["episodes"][0]["title"] = "Different story"
    forged["head"] = digest({k: v for k, v in forged.items() if k != "head"})
    with pytest.raises(CampaignError, match="source changed"):
        verify_campaign(forged)


def test_completed_journal_cannot_be_substituted():
    session = _play_first()
    forged = deepcopy(session)
    forged["completed"][0]["state"]["health"] = 999
    forged["head"] = digest({k: v for k, v in forged.items() if k != "head"})
    with pytest.raises(CampaignError):
        verify_campaign(forged)


def test_unearned_ending_does_not_advance_and_retry_is_bounded():
    source = _source()
    source["episodes"] = [source["episodes"][0]]
    source["episodes"][0]["ending"] = "salvage"
    session = open_campaign(source)
    for action in acceptance_actions("protect"):
        session = step_campaign(session, action, expected_head=session["head"])
    assert verify_campaign(session)["index"] == 0
    assert verify_campaign(session)["status"] == "won:protect"
    for count in range(3):
        session = retry_campaign(session, expected_head=session["head"])
        assert session["retries"][0] == count + 1
        for action in acceptance_actions("protect"):
            session = step_campaign(session, action, expected_head=session["head"])
    with pytest.raises(CampaignError, match="budget"):
        retry_campaign(session, expected_head=session["head"])


def test_invalid_source_rejected():
    source = _source()
    source["episodes"].append(deepcopy(source["episodes"][0]))
    with pytest.raises(CampaignError, match="duplicate"):
        parse_campaign(source)
    source = _source()
    source["episodes"][0]["ending"] = "admin-win"
    with pytest.raises(CampaignError, match="ending"):
        parse_campaign(source)
    source = _source()
    source["episodes"][0]["world"]["start"] = [-1, 0]
    with pytest.raises(CampaignError, match="world"):
        parse_campaign(source)


def test_export_tampering_rejected():
    bundle = export_campaign(_play_first())
    bundle["payload"]["session"]["index"] = 2
    with pytest.raises(CampaignError, match="digest"):
        verify_export(bundle)


def test_terminal_open_inspect_and_export(tmp_path, capsys):
    output = tmp_path / "save.json"
    assert main(["open", "--source", str(SOURCE), "--output", str(output)]) == 0
    session = json.loads(output.read_text())
    assert main(["inspect", "--session", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["head"] == session["head"]
    assert report["actions"]
    export_path = tmp_path / "export.json"
    assert main(["export", "--session", str(output), "--output", str(export_path)]) == 0
    assert main(["verify", "--bundle", str(export_path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_completed_campaign_with_single_chapter():
    source = _source()
    source["episodes"] = source["episodes"][:1]
    session = open_campaign(source)
    for action in acceptance_actions("protect"):
        session = step_campaign(session, action, expected_head=session["head"])
    verified = verify_campaign(session)
    assert verified["status"] == "completed"
    assert verified["index"] == 1
    assert verified["actions"] == []
    with pytest.raises(CampaignError, match="completed"):
        step_campaign(session, {"verb": "rest"}, expected_head=session["head"])


def test_two_original_chapters_reach_earned_ending_and_export():
    from skeleton.game.gameplay.ridge_rescue.campaign_acceptance import run_acceptance
    bundle = run_acceptance()
    result = verify_export(bundle)
    assert result["index"] == 2
    assert result["status"] == "completed"
    assert [entry["state"]["status"] for entry in result["session"]["completed"]] == [
        "won:protect", "won:salvage"
    ]
    assert result["session"]["completed"][1]["state"]["health"] > 0


def test_demo_cli_replays_both_chapters(tmp_path):
    path = tmp_path / "complete.json"
    assert main(["demo", "--output", str(path)]) == 0
    result = verify_export(path.read_bytes())
    assert result["status"] == "completed"
    assert result["index"] == 2
