"""Original capsule -> real movement -> pickup -> craft -> quest -> reopen."""
from __future__ import annotations

import copy
import json
import socket

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_play_session import start_play_session
from skeleton.ai.runtime.game_play_quest import (
    GameQuestError, MANIFEST_SCHEMA, pack_quest_overlay,
    validate_quest_manifest, verify_quest_overlay,
)
from skeleton.app.cli import run_app_cli


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def _control():
    return {"left": False, "right": False, "jump": False}


def _manifest(capsule, position):
    return {
        "schema_version": MANIFEST_SCHEMA,
        "capsule_sha256": capsule["capsule_sha256"],
        "collectibles": [
            {"id": "ore-1", "item_id": "ore", "x": position["x"],
             "y": position["y"], "amount": 2},
        ],
        "recipes": [
            {"id": "forge-key", "costs": [{"item_id": "ore", "amount": 2}],
             "output": {"item_id": "key", "amount": 1}},
        ],
        "quests": [
            {"id": "open-gate", "requires": [],
             "costs": [{"item_id": "key", "amount": 1}],
             "reward": {"item_id": "medal", "amount": 1}},
        ],
    }


def _setup():
    capsule = _capsule()
    session = start_play_session(capsule, [_control()])
    manifest = _manifest(capsule, session["final_avatar"])
    actions = [{"craft": "forge-key", "claim": "open-gate"}]
    return capsule, session, manifest, actions


def test_full_pickup_craft_quest_replay_and_durable_save():
    capsule, session, manifest, actions = _setup()
    overlay = pack_quest_overlay(capsule, session, manifest, actions)
    assert overlay == pack_quest_overlay(capsule, session, manifest, actions)
    receipt = verify_quest_overlay(capsule, overlay)
    assert receipt["overlay_replay_verified"]
    assert receipt["inventory"] == {"medal": 1}
    assert receipt["picked_collectibles"] == ["ore-1"]
    assert receipt["claimed_quests"] == ["open-gate"]
    assert [e["type"] for e in receipt["events"]] == ["pickup", "craft", "quest"]
    assert receipt["victory_frame"] == session["victory_frame"]
    assert not receipt["native_export_created"]
    assert not receipt["independent_rights_review_completed"]


def test_claim_without_crafting_fails_closed():
    capsule, session, manifest, _ = _setup()
    with pytest.raises(GameQuestError, match="inventory"):
        pack_quest_overlay(
            capsule, session, manifest, [{"craft": None, "claim": "open-gate"}],
        )


def test_crafting_cannot_duplicate_or_spend_nonexistent_items():
    capsule, session, manifest, _ = _setup()
    twice = start_play_session(capsule, [_control(), _control()])
    actions = [
        {"craft": "forge-key", "claim": "open-gate"},
        {"craft": "forge-key", "claim": None},
    ]
    with pytest.raises(GameQuestError, match="inventory"):
        pack_quest_overlay(capsule, twice, manifest, actions)


def test_unknown_recipes_and_claims_are_rejected():
    capsule, session, manifest, _ = _setup()
    for action in (
        {"craft": "missing", "claim": None},
        {"craft": None, "claim": "missing"},
    ):
        with pytest.raises(GameQuestError):
            pack_quest_overlay(capsule, session, manifest, [action])


@pytest.mark.parametrize("mutate", [
    lambda m: m["collectibles"][0].update(x=True),
    lambda m: m["collectibles"][0].update(id="UPPERCASE"),
    lambda m: m["collectibles"].append(copy.deepcopy(m["collectibles"][0])),
    lambda m: m["recipes"][0]["costs"].append({"item_id": "ore", "amount": 1}),
    lambda m: m["quests"][0].update(requires=["open-gate"]),
    lambda m: m["quests"][0].update(requires=["missing"]),
    lambda m: m["quests"][0].update(reward={"item_id": "medal", "amount": 0}),
    lambda m: m.update(unknown="privileged"),
    lambda m: m.update(capsule_sha256="0" * 64),
])
def test_manifest_rejects_invalid_authoring(mutate):
    capsule, session, manifest, _ = _setup()
    mutate(manifest)
    with pytest.raises(GameQuestError):
        validate_quest_manifest(capsule, manifest)


@pytest.mark.parametrize("mutate", [
    lambda o: o["result"]["inventory"].update(medal=99),
    lambda o: o["result"]["events"][0].update(type="admin"),
    lambda o: o["result"].update(victory_frame=1),
    lambda o: o["result"].update(frame_count=True),
    lambda o: o["session"].update(trace_sha256="0" * 64),
    lambda o: o["actions"][0].update(claim=None),
    lambda o: o["manifest"]["recipes"][0].update(id="forged"),
    lambda o: o.update(body_sha256="0" * 64),
    lambda o: o.update(extra=True),
])
def test_replay_rejects_forged_overlay(mutate):
    capsule, session, manifest, actions = _setup()
    overlay = pack_quest_overlay(capsule, session, manifest, actions)
    mutate(overlay)
    with pytest.raises((GameQuestError, ValueError)):
        verify_quest_overlay(capsule, overlay)


def test_source_modification_invalidates_quest_overlay():
    capsule, session, manifest, actions = _setup()
    overlay = pack_quest_overlay(capsule, session, manifest, actions)
    altered = copy.deepcopy(capsule)
    altered["tilemap"][1] = altered["tilemap"][1].replace("S", ".")
    with pytest.raises(ValueError):
        verify_quest_overlay(altered, overlay)


def test_canonical_app_cli_runs_real_quest_gameplay_offline(tmp_path, capsys, monkeypatch):
    def deny_network(*_args, **_kwargs):
        raise AssertionError("gameplay quest must never contact network")
    monkeypatch.setattr(socket, "create_connection", deny_network)
    capsule, session, manifest, actions = _setup()
    source = tmp_path / "capsule.json"
    save = tmp_path / "session.json"
    rules = tmp_path / "quests.json"
    choices = tmp_path / "actions.json"
    overlay = tmp_path / "overlay.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    save.write_text(json.dumps(session), encoding="utf-8")
    rules.write_text(json.dumps(manifest), encoding="utf-8")
    choices.write_text(json.dumps({"actions": actions}), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--play-quest-overlay", str(save),
        "--session-capsule", str(source), "--quest-manifest", str(rules),
        "--quest-actions", str(choices), "--quest-output", str(overlay),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["inventory"] == {"medal": 1}
    assert overlay.exists()
    assert main([
        "--verify-quest-overlay", str(overlay), "--session-capsule", str(source),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["overlay_replay_verified"]


def test_quest_cli_refuses_existing_output_or_untrusted_symlink(tmp_path, capsys):
    capsule, session, manifest, actions = _setup()
    source = tmp_path / "capsule.json"
    save = tmp_path / "save.json"
    rules = tmp_path / "manifest.json"
    choices = tmp_path / "actions.json"
    output = tmp_path / "existing.json"
    for path, value in (
        (source, capsule), (save, session), (rules, manifest),
        (choices, {"actions": actions}),
    ):
        path.write_text(json.dumps(value), encoding="utf-8")
    output.write_text("original", encoding="utf-8")
    args = [
        "--play-quest-overlay", str(save), "--session-capsule", str(source),
        "--quest-manifest", str(rules), "--quest-actions", str(choices),
        "--quest-output", str(output),
    ]
    assert main(args) == 1
    assert output.read_text() == "original"
    capsys.readouterr()
    assert main(["--catalog", "--quest-output", str(output)]) == 2
    link = tmp_path / "link.json"
    try:
        link.symlink_to(save)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unsupported")
    assert main([
        "--play-quest-overlay", str(link), "--session-capsule", str(source),
        "--quest-manifest", str(rules), "--quest-actions", str(choices),
        "--quest-output", str(tmp_path / "fresh.json"),
    ]) == 1
    assert not (tmp_path / "fresh.json").exists()
