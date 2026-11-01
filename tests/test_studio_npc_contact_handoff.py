"""NPC contact eligibility bound to actual walk movement and authored patrols."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import replay_walk
from skeleton.ai.game_builder.studio_npc_contact_handoff import (
    FILENAME, compile_npc_contact_handoff, replay_npc_contact_handoff,
    render_npc_contact_handoff_html, publish_npc_contact_handoff,
    restore_npc_contact_handoff,
)

DIGEST = "a" * 64


@pytest.fixture
def source(monkeypatch):
    import skeleton.ai.game_builder.studio_ecosystem_walk_replay as walk
    import skeleton.ai.game_builder.studio_ecosystem_encounters as encounters
    import skeleton.ai.game_builder.studio_ecosystem_npc_patrol as patrol
    import skeleton.ai.game_builder.studio_npc_contact_handoff as contact
    world = {
        "project_id": "original", "source_digest": DIGEST,
        "width": 6, "height": 5, "spawn": [1, 1], "target": [4, 3],
        "maps": [["######", "#....#", "#.##.#", "#....#", "######"]],
        "stages": [{"id": "s1", "alternatives": ["continue"], "prerequisites": []}],
    }
    hazards = {
        "project_id": "original", "source_digest": DIGEST,
        "starting_health": 2, "hazard_damage": 1,
        "hazards_by_stage": [[[4, 1]]],
    }
    cast = {
        "project_id": "original", "source_digest": DIGEST,
        "actors": [{"id": "archivist", "name": "Archivist",
                    "knows": "The north gate is sealed.",
                    "patrol_by_stage": [[[2, 1], [3, 1]]]}],
    }
    monkeypatch.setattr(walk, "playable_world_source", lambda _: world)
    monkeypatch.setattr(encounters, "playable_world_source", lambda _: world)
    monkeypatch.setattr(encounters, "authored_hazards", lambda _: hazards)
    monkeypatch.setattr(patrol, "cast_patrols", lambda _: cast)
    monkeypatch.setattr(contact, "cast_patrols", lambda _: cast)
    return {"original": True}, world, hazards, cast


def plan(source, session=None, npc_id="archivist"):
    if session is None:
        session = replay_walk(source[0], [], authorized=True).receipt()
    return compile_npc_contact_handoff(
        source[0], session, npc_id=npc_id, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=session["session_digest"],
    )


def test_authored_npc_proximity_is_replayed_not_fabricated(source):
    receipt = plan(source)
    assert receipt["playable_contact_eligible"] is True
    assert receipt["npc_conversation_performed"] is False
    assert receipt["authored_knowledge"] == "The north gate is sealed."
    assert receipt["npc_patrol_position"] == [2, 1]
    assert replay_npc_contact_handoff(
        source[0], receipt, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=receipt["session_digest"],
    ) == receipt
    assert b"default-src 'none'" in render_npc_contact_handoff_html(
        source[0], receipt, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=receipt["session_digest"],
    )


def test_npc_patrol_clock_tracks_actual_accepted_moves(source):
    session = replay_walk(
        source[0], [("move", "right")], authorized=True,
    ).receipt()
    receipt = plan(source, session)
    assert receipt["accepted_moves"] == 1
    assert receipt["player_position"] == [2, 1]
    assert receipt["npc_patrol_position"] == [3, 1]


def test_far_contact_and_unknown_npc_fail_closed(source):
    session = replay_walk(
        source[0], [("move", "right"), ("move", "right")],
        authorized=True,
    ).receipt()
    # At x=3 after two moves; NPC at x=2, still adjacent.
    assert plan(source, session)["playable_contact_eligible"]
    session = replay_walk(
        source[0], [("move", "right"), ("move", "right"),
                    ("move", "right"), ("move", "down"),
                    ("move", "down")], authorized=True,
    ).receipt()
    with pytest.raises(StudioQuestError, match="proximity"):
        plan(source, session)
    with pytest.raises(StudioQuestError, match="unregistered"):
        plan(source, npc_id="invented")


def test_forged_contact_and_cast_drift_fail(source):
    receipt = plan(source)
    forged = deepcopy(receipt)
    forged["authored_knowledge"] = "unearned secret"
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_npc_contact_handoff(
            source[0], forged, authorized=True,
            expected_source_digest=DIGEST,
            expected_session_digest=receipt["session_digest"],
        )
    source[3]["source_digest"] = "b" * 64
    with pytest.raises(StudioQuestError, match="custody"):
        plan(source)


def test_authority_and_private_publication(source, tmp_path):
    receipt = plan(source)
    with pytest.raises(PermissionError):
        compile_npc_contact_handoff(
            source[0], receipt["walk_receipt"], npc_id="archivist",
            authorized=False, expected_source_digest=DIGEST,
            expected_session_digest=receipt["session_digest"],
        )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert publish_npc_contact_handoff(
        source[0], receipt, private, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=receipt["session_digest"],
    )["file_write_performed"]
    assert restore_npc_contact_handoff(
        source[0], private, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=receipt["session_digest"],
    ) == receipt
    with pytest.raises(FileExistsError):
        publish_npc_contact_handoff(
            source[0], receipt, private, authorized=True,
            expected_source_digest=DIGEST,
            expected_session_digest=receipt["session_digest"],
        )
    target = private / FILENAME
    target.write_text('{"schema":"one","schema":"two"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_npc_contact_handoff(
            source[0], private, authorized=True,
            expected_source_digest=DIGEST,
            expected_session_digest=receipt["session_digest"],
        )
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_npc_contact_handoff(
            source[0], private, authorized=True,
            expected_source_digest=DIGEST,
            expected_session_digest=receipt["session_digest"],
        )


def test_cli_and_jeeves_contact_parity(source, tmp_path, monkeypatch, capsys):
    import scripts.studio_npc_contact_handoff_cli as cli
    import skeleton.ai.agents.jeeves.studio_npc_contact_handoff_tool as adapter
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    monkeypatch.setattr(cli, "read_blueprint", lambda _: source[0])
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: source[0])
    session = replay_walk(source[0], [], authorized=True).receipt()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert cli.main([
        "--project", "original", "--expected-source", DIGEST,
        "--session-json", json.dumps(session),
        "--expected-session", session["session_digest"],
        "--npc-id", "archivist", "--publish", str(private),
        "--html-sha256",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["file_write_performed"]
    assert cli.main([
        "--project", "original", "--expected-source", DIGEST,
        "--expected-session", session["session_digest"],
        "--restore", str(private),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["npc_contact"] == output["npc_contact"]
    request = {
        "schema": adapter.REQUEST_SCHEMA, "project_id": "original",
        "expected_source_digest": DIGEST,
        "expected_session_digest": session["session_digest"],
        "session_receipt": session, "npc_id": "archivist",
    }
    direct = adapter.execute_npc_contact_handoff_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_contact_handoff", "arguments": request},
        authorized=True,
    )
    assert direct["detail"] == output["npc_contact"]
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False


def test_untrusted_jeeves_request_cannot_grant_authority(source, monkeypatch):
    import skeleton.ai.agents.jeeves.studio_npc_contact_handoff_tool as adapter
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: source[0])
    session = replay_walk(source[0], [], authorized=True).receipt()
    request = {
        "schema": adapter.REQUEST_SCHEMA, "project_id": "original",
        "expected_source_digest": DIGEST,
        "expected_session_digest": session["session_digest"],
        "session_receipt": session, "npc_id": "archivist",
    }
    with pytest.raises(PermissionError):
        adapter.execute_npc_contact_handoff_tool(request, authorized=False)
    with pytest.raises(StudioQuestError, match="authority"):
        route_world_tool(
            {"tool": "studio_original_npc_contact_handoff",
             "arguments": {**request, "authorized": True}},
            authorized=True,
        )


def test_cast_snapshot_must_match_contact_observation(source, monkeypatch):
    import skeleton.ai.game_builder.studio_npc_contact_handoff as contact
    monkeypatch.setattr(contact, "inspect_npc_contact", lambda *args, **kwargs: {
        "project_id": "original", "npc_id": "archivist",
        "local_contact_available": True, "real_dialogue_performed": False,
        "patrol_position": [2, 1], "authored_knowledge": "forged",
    })
    with pytest.raises(StudioQuestError, match="diverged"):
        plan(source)
