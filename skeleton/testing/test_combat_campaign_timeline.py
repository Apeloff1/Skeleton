"""Campaign timeline accounting, portable restart and tamper rejection."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.combat_campaign_player import (
    demo_player_campaign, export_player_campaign, import_player_campaign,
    new_player_campaign, verify_player_campaign,
)
from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_timeline import (
    audit_player_campaign, cli, export_player_timeline,
    import_player_timeline, resume_player_timeline, verify_player_timeline,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_timeline_replays_original_campaign_and_conserves_rewards():
    session = demo_player_campaign()
    report = audit_player_campaign(session)
    assert verify_player_timeline(session, report) == report
    assert report["event_count"] == len(session["journal"])
    assert report["earned_currency"] == session["state"]["currency"]
    assert report["phase"] == session["state"]["phase"]
    assert report["entries"][-1]["after_state_digest"] == session["state_digest"]
    assert all(item["earned_currency"] >= 0 for item in report["entries"])
    assert sum(item["earned_currency"] for item in report["entries"]) == report["earned_currency"]
    assert all(item["action_receipt"] == session["journal"][i]["receipt"]
               for i, item in enumerate(report["entries"]))


def test_empty_player_campaign_has_empty_timeline():
    session = new_player_campaign(original_campaign())
    report = audit_player_campaign(session)
    assert report["event_count"] == 0
    assert report["earned_currency"] == 0
    assert report["entries"] == []
    assert report["last_event_receipt"] is None


def test_portable_timeline_round_trip_and_resume_no_actions():
    session = demo_player_campaign()
    bundle = export_player_timeline(session)
    assert import_player_timeline(bundle) == session
    assert import_player_campaign(export_player_campaign(session)) == session
    assert resume_player_timeline(bundle, []) == bundle


def test_timeline_rejects_recomputed_forged_rewards_and_health():
    session = demo_player_campaign()
    report = audit_player_campaign(session)
    for mutate in (
        lambda r: r.update(earned_currency=999),
        lambda r: r.update(hero_hp=999),
        lambda r: r["entries"][0].update(hero_hp_after=999),
        lambda r: r["entries"][0].update(earned_currency=999),
        lambda r: r["entries"][0].update(combat_receipt="0" * 64),
        lambda r: r.update(phase="won_fake"),
        lambda r: r.update(qualification="device_certified"),
    ):
        forged = copy.deepcopy(report)
        mutate(forged)
        forged["checksum"] = dig({k: v for k, v in forged.items()
                                  if k != "checksum"})
        with pytest.raises(CombatSessionError):
            verify_player_timeline(session, forged)


def test_timeline_rejects_portable_source_or_nested_save_swap():
    session = demo_player_campaign()
    bundle = export_player_timeline(session)
    for mutate in (
        lambda b: b.update(source_digest="0" * 64),
        lambda b: b.update(state_digest="0" * 64),
        lambda b: b["game"]["session"]["state"].update(currency=999),
        lambda b: b["timeline"].update(earned_currency=999),
    ):
        forged = copy.deepcopy(bundle)
        mutate(forged)
        forged["checksum"] = dig({k: v for k, v in forged.items()
                                  if k != "checksum"})
        with pytest.raises(CombatSessionError):
            import_player_timeline(forged)


def test_timeline_cli_end_to_end(capsys):
    from skeleton.__main__ import main
    assert main(["combat-campaign-timeline", "demo"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    session = json.loads(capsys.readouterr().out)
    assert verify_player_campaign(session) == session
    assert cli(["audit", "--session-json", json.dumps(session)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--session-json", json.dumps(session),
                "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli(["resume", "--bundle-json", json.dumps(bundle),
                "--actions-json", "[]"]) == 0
    assert json.loads(capsys.readouterr().out) == bundle


def test_timeline_rejects_duplicate_keys_and_invalid_resume(capsys):
    assert cli(["import", "--bundle-json", '{"x":1,"x":2}']) == 2
    assert "error" in capsys.readouterr().err
    bundle = export_player_timeline(demo_player_campaign())
    assert cli(["resume", "--bundle-json", json.dumps(bundle),
                "--actions-json", '{"not":"a list"}']) == 2
    assert "error" in capsys.readouterr().err
