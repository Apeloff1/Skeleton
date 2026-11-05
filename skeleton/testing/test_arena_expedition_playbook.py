"""Portable combat playbooks must verify every gameplay and accounting seam."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.arena_expedition import (
    original_expedition, simulate_expedition,
)
from skeleton.game.gameplay.arena_expedition_playbook import (
    build_playbook, cli, import_playbook, original_playbook,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _easy_source():
    source = original_expedition()
    for stage in source["arenas"]:
        stage["arena"]["actors"][1]["max_hp"] = 1
        stage["arena"]["actors"][1]["attack"] = 1
    return source


def test_original_playbook_is_replayable_and_portable():
    book = original_playbook()
    final = import_playbook(json.loads(json.dumps(book)))
    assert final["state"]["phase"] == "won"
    assert final["state_digest"] == book["final_state_digest"]
    assert book["audit"]["total_earned"] == 30
    assert book["audit"]["total_spent"] == 5
    assert book["plan"] is None


def test_auto_solver_playbook_contains_witness():
    book = build_playbook(_easy_source())
    assert book["plan"]["status"] == "found"
    assert book["plan"]["actions"] == book["actions"]
    assert import_playbook(book)["state"]["phase"] == "won"


def test_resume_from_verified_save_proves_source_lineage():
    source = _easy_source()
    saved = simulate_expedition(source, [{"kind": "fight"}])
    book = build_playbook(session=saved, actions=[{"kind": "fight"}])
    assert book["initial_state_digest"] == saved["state_digest"]
    assert import_playbook(book)["state"]["phase"] == "won"


def test_manual_unearned_win_rejected():
    with pytest.raises(CombatSessionError, match="earned victory"):
        build_playbook(original_expedition(), actions=[])
    with pytest.raises(CombatSessionError):
        build_playbook(original_expedition(), actions=[
            {"kind": "buy", "item_id": "tide_tonic"},
        ])


@pytest.mark.parametrize("tamper", [
    lambda b: b.update(final_state_digest="0" * 64),
    lambda b: b["audit"].update(balance=999),
    lambda b: b["bundle"].update(checksum="0" * 64),
    lambda b: b["actions"].append({"kind": "fight"}),
    lambda b: b["initial"]["state"].update(currency=999),
    lambda b: b.update(source_digest="0" * 64),
    lambda b: b.update(checksum="0" * 64),
    lambda b: b.update(admin_override=True),
])
def test_any_mutation_of_bundle_or_lineage_rejected(tamper):
    book = copy.deepcopy(original_playbook())
    tamper(book)
    with pytest.raises(CombatSessionError):
        import_playbook(book)


def test_checksum_recomputation_cannot_forge_gameplay():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    book = copy.deepcopy(original_playbook())
    book["audit"]["balance"] = 999
    book["checksum"] = dig({k: v for k, v in book.items() if k != "checksum"})
    with pytest.raises(CombatSessionError, match="audit"):
        import_playbook(book)


def test_missing_source_and_actions_rejected():
    with pytest.raises(CombatSessionError):
        build_playbook()
    with pytest.raises(CombatSessionError):
        build_playbook(original_expedition(), session={"bad": True})
    with pytest.raises(CombatSessionError):
        build_playbook(original_expedition(), actions="fight")


def test_cli_demo_verify_and_canonical_entry(capsys):
    assert cli(["demo"]) == 0
    book = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--playbook-json", json.dumps(book)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["phase"] == "won"
    from skeleton.__main__ import main
    assert main(["combat-expedition-playbook", "demo"]) == 0
    assert import_playbook(json.loads(capsys.readouterr().out))["state"]["phase"] == "won"


def test_cli_rejects_bad_json(capsys):
    assert cli(["verify", "--playbook-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
