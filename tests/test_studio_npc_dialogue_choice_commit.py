"""NPC dialogue choice receipts must replay from playable contact, not inference."""
from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_dialogue_choice_commit import (
    FILENAME, compile_npc_dialogue_choice_commit,
    replay_npc_dialogue_choice_commit, publish_npc_dialogue_choice_commit,
    restore_npc_dialogue_choice_commit,
)

SOURCE = "a" * 64
WALK = "b" * 64
QUEST = "c" * 64
CONTACT = "d" * 64
NEXT_LISTEN = "e" * 64
NEXT_LEAVE = "f" * 64


@pytest.fixture
def harness(monkeypatch):
    import skeleton.ai.game_builder.studio_npc_dialogue_choice_commit as impl
    import skeleton.ai.agents.jeeves.studio_npc_dialogue_choice_commit_tool as adapter
    import scripts.studio_npc_dialogue_choice_commit_cli as cli

    contact = {
        "receipt_digest": CONTACT, "project_id": "original",
        "npc_id": "archivist", "scene_id": "first",
        "playable_proximity_verified": True,
        "quest_unlock_replay_verified": True,
        "quest_choice_committed": False,
        "dialogue_spoken_verified": False, "file_write_performed": False,
        "quest_actions": [],
        "dialogue_card": {
            "status": "available", "npc_id": "archivist",
            "scene_id": "first", "quest_stage": "gate",
            "card_digest": "1" * 64,
        },
        "choice_previews": [
            {
                "npc_id": "archivist", "scene_id": "first",
                "quest_stage": "gate", "card_digest": "1" * 64,
                "alternative": alternative,
                "before_session_digest": QUEST,
                "after_session_digest": digest,
                "preview_digest": "2" * 64 if alternative == "listen" else "3" * 64,
                "choice_committed": False, "external_evidence_verified": False,
            }
            for alternative, digest in (("listen", NEXT_LISTEN),
                                        ("leave", NEXT_LEAVE))
        ],
    }
    docs = {"original": True}

    def contact_replay(source, receipt, **kwargs):
        if receipt != contact or source != docs:
            raise StudioQuestError("contact replay proof mismatch")
        if kwargs["expected_source_digest"] != SOURCE:
            raise StudioQuestError("source lease mismatch")
        if kwargs["expected_walk_digest"] != WALK:
            raise StudioQuestError("walk lease mismatch")
        if kwargs["expected_quest_digest"] != QUEST:
            raise StudioQuestError("quest lease mismatch")
        return deepcopy(contact)

    def quest_replay(source, actions, *, authorized):
        if source != docs or authorized is not True:
            raise StudioQuestError("quest source or authority mismatch")
        if len(actions) != 1 or actions[0][0] != "gate":
            raise StudioQuestError("invalid committed quest actions")
        choice = actions[0][1]
        if choice not in ("listen", "leave"):
            raise StudioQuestError("unknown quest choice")
        return SimpleNamespace(
            digest=NEXT_LISTEN if choice == "listen" else NEXT_LEAVE,
            project_id="original", source_digest=SOURCE,
            choices=[("gate", choice)],
        )

    monkeypatch.setattr(impl, "replay_npc_dialogue_contact", contact_replay)
    monkeypatch.setattr(impl, "replay_quest", quest_replay)
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    return docs, contact


def params():
    return {
        "authorized": True, "expected_contact_digest": CONTACT,
        "expected_source_digest": SOURCE, "expected_walk_digest": WALK,
        "expected_quest_digest": QUEST,
    }


def make(harness, alternative="listen", **changes):
    options = params()
    options.update(changes)
    return compile_npc_dialogue_choice_commit(
        harness[0], harness[1], alternative=alternative, **options)


def test_choice_commits_only_a_replayable_authored_quest_transition(harness):
    receipt = make(harness)
    assert receipt["quest_actions"] == [["gate", "listen"]]
    assert receipt["next_quest_session_digest"] == NEXT_LISTEN
    assert receipt["choice_receipt_committed"]
    assert receipt["quest_choice_replayed"]
    assert receipt["playable_proximity_verified"]
    assert not receipt["dialogue_spoken_verified"]
    assert not receipt["external_evidence_verified"]
    assert not receipt["native_runtime_verified"]
    assert not receipt["file_write_performed"]
    assert not receipt["release_certified"]
    assert replay_npc_dialogue_choice_commit(
        harness[0], receipt, **params()) == receipt
    assert make(harness, "leave")["next_quest_session_digest"] == NEXT_LEAVE


def test_missing_authority_stale_leases_and_unknown_choices_fail(harness):
    with pytest.raises(PermissionError):
        make(harness, authorized=False)
    with pytest.raises(StudioQuestError, match="stale"):
        make(harness, expected_contact_digest="0" * 64)
    with pytest.raises(StudioQuestError, match="uniquely authored"):
        make(harness, "invented")
    with pytest.raises(StudioQuestError, match="alternative"):
        make(harness, "listen\n")
    with pytest.raises(StudioQuestError, match="alternative"):
        make(harness, "bad\ud800")


def test_locked_contact_preview_and_consequence_drift_fail(harness, monkeypatch):
    import skeleton.ai.game_builder.studio_npc_dialogue_choice_commit as impl
    harness[1]["dialogue_card"]["status"] = "locked"
    with pytest.raises(StudioQuestError, match="not available"):
        make(harness)
    harness[1]["dialogue_card"]["status"] = "available"
    harness[1]["choice_previews"][0]["after_session_digest"] = "9" * 64
    with pytest.raises(StudioQuestError, match="consequence drift"):
        make(harness)
    harness[1]["choice_previews"][0]["after_session_digest"] = NEXT_LISTEN
    harness[1]["choice_previews"][0]["external_evidence_verified"] = True
    with pytest.raises(StudioQuestError, match="proof diverged"):
        make(harness)
    harness[1]["choice_previews"][0]["external_evidence_verified"] = False
    original = impl.replay_quest

    def mutate(source, actions, *, authorized):
        result = original(source, actions, authorized=authorized)
        source["unwanted"] = "changed"
        return result

    monkeypatch.setattr(impl, "replay_quest", mutate)
    with pytest.raises(StudioQuestError, match="source changed"):
        make(harness)


def test_replay_rejects_forged_receipt_and_tampered_embedded_contact(harness):
    receipt = make(harness)
    forged = deepcopy(receipt)
    forged["next_quest_session_digest"] = "0" * 64
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_npc_dialogue_choice_commit(harness[0], forged, **params())
    forged = deepcopy(receipt)
    forged["contact_receipt"]["quest_actions"].append(["gate", "listen"])
    with pytest.raises(StudioQuestError, match="contact replay"):
        replay_npc_dialogue_choice_commit(harness[0], forged, **params())


def test_private_publication_restore_and_fail_closed_file_checks(harness, tmp_path):
    receipt = make(harness)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    published = publish_npc_dialogue_choice_commit(
        harness[0], receipt, private, **params())
    assert published["file_write_performed"]
    assert published["receipt_digest"] == receipt["receipt_digest"]
    assert restore_npc_dialogue_choice_commit(
        harness[0], private, **params()) == receipt
    with pytest.raises(FileExistsError):
        publish_npc_dialogue_choice_commit(harness[0], receipt, private, **params())
    target = private / FILENAME
    target.write_text('{"schema":"a","schema":"b"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_npc_dialogue_choice_commit(harness[0], private, **params())
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_npc_dialogue_choice_commit(harness[0], private, **params())


def test_jeeves_authoring_gate_router_and_cli_parity(harness, capsys):
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    from skeleton.ai.agents.jeeves.studio_npc_dialogue_choice_commit_tool import (
        REQUEST_SCHEMA, execute_npc_dialogue_choice_commit_tool,
    )
    from scripts.studio_npc_dialogue_choice_commit_cli import main

    request = {
        "schema": REQUEST_SCHEMA, "project_id": "original",
        "contact_receipt": harness[1], "alternative": "listen",
        "expected_contact_digest": CONTACT,
        "expected_source_digest": SOURCE,
        "expected_walk_digest": WALK, "expected_quest_digest": QUEST,
    }
    direct = execute_npc_dialogue_choice_commit_tool(request, authorized=True)
    with pytest.raises(PermissionError):
        route_world_tool(
            {"tool": "studio_original_npc_dialogue_choice_commit",
             "arguments": request}, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_dialogue_choice_commit",
         "arguments": request}, authorized=True, allow_authoring=True)
    assert routed["result"] == direct
    assert not routed["file_write_performed"]
    assert main([
        "--project", "original", "--expected-contact", CONTACT,
        "--expected-source", SOURCE, "--expected-walk", WALK,
        "--expected-quest", QUEST, "--contact-json", json.dumps(harness[1]),
        "--alternative", "listen",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["choice_commit"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_npc_dialogue_choice_commit_tool(request, authorized=False)
    with pytest.raises(StudioQuestError, match="authority"):
        route_world_tool(
            {"tool": "studio_original_npc_dialogue_choice_commit",
             "arguments": {**request, "authorized": True}},
            authorized=True, allow_authoring=True)

def test_offline_html_escapes_authored_content_and_never_executes(harness, capsys):
    from skeleton.ai.game_builder.studio_npc_dialogue_choice_commit import (
        render_npc_dialogue_choice_commit_html,
    )
    from scripts.studio_npc_dialogue_choice_commit_cli import main

    harness[1]["npc_id"] = "<img src=x onerror=alert(1)>"
    harness[1]["dialogue_card"]["npc_id"] = harness[1]["npc_id"]
    for preview in harness[1]["choice_previews"]:
        preview["npc_id"] = harness[1]["npc_id"]
    receipt = make(harness)
    page = render_npc_dialogue_choice_commit_html(
        harness[0], receipt, **params()).decode("utf-8")
    assert "default-src 'none'" in page
    assert "script-src 'none'" in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert "<img src=x" not in page
    assert "not spoken dialogue" in page
    assert main([
        "--project", "original", "--expected-contact", CONTACT,
        "--expected-source", SOURCE, "--expected-walk", WALK,
        "--expected-quest", QUEST, "--contact-json", json.dumps(harness[1]),
        "--alternative", "listen", "--html-preview",
    ]) == 0
    assert "Content-Security-Policy" in capsys.readouterr().out


def test_html_preview_is_authority_bound_and_publication_is_exclusive(harness, tmp_path):
    from skeleton.ai.game_builder.studio_npc_dialogue_choice_commit import (
        render_npc_dialogue_choice_commit_html,
    )
    receipt = make(harness)
    with pytest.raises(PermissionError):
        render_npc_dialogue_choice_commit_html(
            harness[0], receipt, **{**params(), "authorized": False})
    with pytest.raises(StudioQuestError, match="canonical replay"):
        render_npc_dialogue_choice_commit_html(
            harness[0], {**receipt, "release_certified": True}, **params())
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    publish_npc_dialogue_choice_commit(harness[0], receipt, private, **params())
    target = private / FILENAME
    target.chmod(0o644)
    with pytest.raises(StudioQuestError, match="private"):
        restore_npc_dialogue_choice_commit(harness[0], private, **params())

def test_cli_private_contact_file_supports_large_receipts_and_rejects_links(
    harness, tmp_path, capsys,
):
    from scripts.studio_npc_dialogue_choice_commit_cli import main
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    source = private / "contact.json"
    source.write_text(json.dumps(harness[1]))
    source.chmod(0o600)
    args = [
        "--project", "original", "--expected-contact", CONTACT,
        "--expected-source", SOURCE, "--expected-walk", WALK,
        "--expected-quest", QUEST, "--contact-file", str(source),
        "--alternative", "leave",
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)[
        "choice_commit"]["next_quest_session_digest"] == NEXT_LEAVE
    source.chmod(0o644)
    with pytest.raises(SystemExit):
        main(args)
    source.unlink()
    source.symlink_to(private / "missing")
    with pytest.raises(SystemExit):
        main(args)
