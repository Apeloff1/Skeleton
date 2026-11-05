"""Original source editing, optimistic concurrency and replay acceptance."""
import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.quest_chapter_campaign import (
    demo_campaign_actions, normalize_campaign, original_campaign,
    simulate_campaign,
)
from skeleton.game.gameplay.quest_chapter_campaign_author import (
    apply_edits, cli, original_edit_demo, save_compatibility, verify_edits,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_editor_preview_reaches_won_with_earned_flag():
    receipt = original_edit_demo()
    assert receipt["preview"]["state"]["phase"] == "won"
    assert "night_shift" in receipt["preview"]["state"]["flags"]
    assert verify_edits(json.loads(json.dumps(receipt))) == receipt


def test_saved_games_are_not_transplanted_between_source_versions():
    old = simulate_campaign(original_campaign(), demo_campaign_actions()[:3])
    edit = original_edit_demo()
    status = save_compatibility(edit, old)
    assert status["compatible"] is False
    assert status["action"] == "restart_from_new_source"


def test_digest_fenced_transaction_and_atomic_rollback():
    source = original_campaign()
    original = copy.deepcopy(source)
    digest = dig(normalize_campaign(source))
    with pytest.raises(CombatSessionError, match="optimistic"):
        apply_edits(source, [
            {"op": "set_granted_flags", "id": "night_watch", "value": ["shift"]}
        ], expected_digest="0" * 64)
    with pytest.raises(CombatSessionError, match="unearned"):
        apply_edits(source, [
            {"op": "set_required_flags", "id": "beacon", "value": ["shift"]}
        ], expected_digest=digest)
    assert source == original


def test_replace_quest_and_ending_revalidate_all_contracts():
    source = original_campaign()
    digest = dig(normalize_campaign(source))
    bad = copy.deepcopy(source["chapters"][0]["quest"])
    bad["world_id"] = "wrong_world"
    with pytest.raises(CombatSessionError):
        apply_edits(source, [
            {"op": "replace_quest", "id": "beacon", "value": bad}
        ], expected_digest=digest)
    with pytest.raises(CombatSessionError, match="not authored"):
        apply_edits(source, [
            {"op": "set_required_ending", "id": "beacon", "value": "missing"}
        ], expected_digest=digest)


def test_append_remove_and_cross_chapter_unlock_rules():
    source = original_campaign()
    digest = dig(normalize_campaign(source))
    third = copy.deepcopy(source["chapters"][1])
    third["id"] = "last_lantern"
    third["quest"]["quest_id"] = "last_lantern_quest"
    third["requires_flags"] = ["harbor_secured"]
    third["grants_flags"] = ["last_lantern_lit"]
    appended = apply_edits(source, [
        {"op": "append_chapter", "value": third}
    ], expected_digest=digest)
    assert len(appended["source"]["chapters"]) == 3
    assert verify_edits(appended) == appended
    removed = apply_edits(appended["source"], [
        {"op": "remove_last_chapter", "id": "last_lantern"}
    ], expected_digest=appended["source_digest"])
    assert len(removed["source"]["chapters"]) == 2
    with pytest.raises(CombatSessionError, match="last chapter"):
        apply_edits(source, [
            {"op": "remove_last_chapter", "id": "beacon"}
        ], expected_digest=digest)


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(before_digest="0" * 64),
    lambda x: x["operations"][0].update(value=["forged"]),
    lambda x: x["source"]["chapters"][1].update(required_ending="quiet_victory"),
    lambda x: x["preview"]["state"].update(phase="blocked"),
    lambda x: x.update(operations_digest="0" * 64),
])
def test_forged_edit_receipt_is_rejected(mutation):
    receipt = original_edit_demo()
    bad = copy.deepcopy(receipt)
    mutation(bad)
    with pytest.raises(CombatSessionError):
        verify_edits(bad)


def test_cli_authoring_and_invalid_source(capsys):
    from skeleton.__main__ import main
    assert main(["quest-campaign-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preview"]["state"]["phase"] == "won"
    assert cli(["verify", "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert cli(["edit", "--source-json", '{"bad":true}',
                "--operations-json", "[]", "--expected-digest", "bad"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
