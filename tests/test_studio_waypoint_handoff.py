"""End-to-end collision and health custody for authored waypoint handoff."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import replay_walk
from skeleton.ai.game_builder.studio_waypoint_handoff import (
    FILENAME, compile_waypoint_handoff, new_walk_receipt,
    replay_waypoint_handoff, publish_waypoint_handoff,
    restore_waypoint_handoff, render_waypoint_handoff_html,
)

DIGEST = "a" * 64


@pytest.fixture
def source(monkeypatch):
    import skeleton.ai.game_builder.studio_waypoint_route as route
    import skeleton.ai.game_builder.studio_waypoint_risk as risk
    import skeleton.ai.game_builder.studio_ecosystem_walk_replay as walk
    import skeleton.ai.game_builder.studio_ecosystem_encounters as encounters
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
    for module in (route, risk, walk):
        monkeypatch.setattr(module, "playable_world_source", lambda _: world)
    monkeypatch.setattr(risk, "authored_hazards", lambda _: hazards)
    monkeypatch.setattr(encounters, "playable_world_source", lambda _: world)
    monkeypatch.setattr(encounters, "authored_hazards", lambda _: hazards)
    return {"original": True}, world, hazards


def plan(source, session=None, *, waypoints=None, hits=0):
    documents = source[0]
    session = session or new_walk_receipt(
        documents, authorized=True, expected_source_digest=DIGEST,
    )
    return compile_waypoint_handoff(
        documents, session, waypoints=[] if waypoints is None else waypoints,
        max_hazard_contacts=hits, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=session["session_digest"],
    )


def test_verified_handoff_replays_authoritative_walk_and_health(source):
    receipt = plan(source)
    assert receipt["accepted_moves"] > 0
    assert receipt["prior_health"] == receipt["post_health"] == 2
    assert receipt["quest_choice_performed"] is False
    assert receipt["playable_handoff_allowed"] is True
    assert receipt["native_runtime_verified"] is False
    assert receipt["post_walk_receipt"]["events"]
    assert replay_waypoint_handoff(
        source[0], receipt, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=receipt["prior_session_digest"],
    ) == receipt
    assert b"default-src 'none'" in render_waypoint_handoff_html(
        source[0], receipt, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=receipt["prior_session_digest"],
    )


def test_resume_from_authoritative_session_not_authored_start(source):
    session = replay_walk(source[0], [("move", "right")], authorized=True).receipt()
    receipt = plan(source, session)
    assert receipt["prior_walk_receipt"] == session
    assert receipt["post_walk_receipt"]["accepted_moves"] == 1 + receipt["accepted_moves"]


def test_hazard_budget_preserves_remaining_health(source):
    source[2]["hazards_by_stage"][0] = [[1, 3], [4, 1]]
    receipt = plan(source, waypoints=[[1, 3]], hits=1)
    assert receipt["post_health"] == 1
    assert len(receipt["new_hazard_contacts"]) == 1
    assert receipt["new_hazard_contacts"][0]["position"] == [1, 3]
    with pytest.raises(StudioQuestError, match="preserve remaining health"):
        plan(source, hits=2)


def test_forged_receipts_and_source_drift_fail_closed(source):
    receipt = plan(source)
    tampered = deepcopy(receipt)
    tampered["post_health"] = 500
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_waypoint_handoff(
            source[0], tampered, authorized=True,
            expected_source_digest=DIGEST,
            expected_session_digest=receipt["prior_session_digest"],
        )
    session = deepcopy(receipt["prior_walk_receipt"])
    session["position"] = [4, 3]
    with pytest.raises(StudioQuestError, match="authoritative"):
        plan(source, session)
    source[2]["source_digest"] = "b" * 64
    with pytest.raises(StudioQuestError):
        plan(source)


def test_wrong_session_authority_and_bad_types(source):
    session = new_walk_receipt(
        source[0], authorized=True, expected_source_digest=DIGEST,
    )
    with pytest.raises(StudioQuestError, match="stale"):
        compile_waypoint_handoff(
            source[0], session, waypoints=[], max_hazard_contacts=0,
            authorized=True, expected_source_digest=DIGEST,
            expected_session_digest="b" * 64,
        )
    with pytest.raises(PermissionError):
        compile_waypoint_handoff(
            source[0], session, waypoints=[], max_hazard_contacts=0,
            authorized=False, expected_source_digest=DIGEST,
            expected_session_digest=session["session_digest"],
        )
    with pytest.raises(StudioQuestError):
        plan(source, hits=True)


def test_private_publication_restore_no_overwrite_or_symlink(source, tmp_path):
    receipt = plan(source)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert publish_waypoint_handoff(
        source[0], receipt, private, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=receipt["prior_session_digest"],
    )["file_write_performed"]
    assert restore_waypoint_handoff(
        source[0], private, authorized=True,
        expected_source_digest=DIGEST,
        expected_session_digest=receipt["prior_session_digest"],
    ) == receipt
    with pytest.raises(FileExistsError):
        publish_waypoint_handoff(
            source[0], receipt, private, authorized=True,
            expected_source_digest=DIGEST,
            expected_session_digest=receipt["prior_session_digest"],
        )
    path = private / FILENAME
    path.write_text('{"schema":"a","schema":"b"}')
    path.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_waypoint_handoff(
            source[0], private, authorized=True,
            expected_source_digest=DIGEST,
            expected_session_digest=receipt["prior_session_digest"],
        )
    path.unlink()
    path.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_waypoint_handoff(
            source[0], private, authorized=True,
            expected_source_digest=DIGEST,
            expected_session_digest=receipt["prior_session_digest"],
        )


def test_cli_and_jeeves_router_produce_same_playable_receipt(source, tmp_path,
                                                              monkeypatch, capsys):
    import scripts.studio_waypoint_handoff_cli as cli
    import skeleton.ai.agents.jeeves.studio_waypoint_handoff_tool as adapter
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    monkeypatch.setattr(cli, "read_blueprint", lambda _: source[0])
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: source[0])
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert cli.main([
        "--project", "original", "--expected-source", DIGEST,
        "--new-session", "--publish", str(private), "--html-sha256",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    receipt = output["handoff"]
    assert output["file_write_performed"] is True
    assert output["publication"]["file_write_performed"] is True
    assert cli.main([
        "--project", "original", "--expected-source", DIGEST,
        "--expected-session", receipt["prior_session_digest"],
        "--restore", str(private),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["handoff"] == receipt
    request = {
        "schema": adapter.REQUEST_SCHEMA, "project_id": "original",
        "expected_source_digest": DIGEST,
        "expected_session_digest": receipt["prior_session_digest"],
        "session_receipt": receipt["prior_walk_receipt"],
        "waypoints": [], "max_hazard_contacts": 0,
    }
    direct = adapter.execute_waypoint_handoff_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_waypoint_handoff", "arguments": request},
        authorized=True,
    )
    assert direct["detail"] == receipt
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False


def test_jeeves_tool_cannot_claim_operator_authority(source, monkeypatch):
    import skeleton.ai.agents.jeeves.studio_waypoint_handoff_tool as adapter
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: source[0])
    session = new_walk_receipt(source[0], authorized=True,
                               expected_source_digest=DIGEST)
    request = {
        "schema": adapter.REQUEST_SCHEMA, "project_id": "original",
        "expected_source_digest": DIGEST,
        "expected_session_digest": session["session_digest"],
        "session_receipt": session, "waypoints": [],
        "max_hazard_contacts": 0,
    }
    with pytest.raises(PermissionError):
        adapter.execute_waypoint_handoff_tool(request, authorized=False)
    with pytest.raises(StudioQuestError, match="authority"):
        route_world_tool(
            {"tool": "studio_original_waypoint_handoff",
             "arguments": {**request, "authorized": True}},
            authorized=True,
        )
