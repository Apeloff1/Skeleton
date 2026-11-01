"""Source-bound risk-aware waypoint route acceptance and negative paths."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_waypoint_risk import (
    FILENAME, compile_waypoint_risk, replay_waypoint_risk,
    render_waypoint_risk_html, publish_waypoint_risk, restore_waypoint_risk,
)

DIGEST = "a" * 64


@pytest.fixture
def source(monkeypatch):
    import skeleton.ai.game_builder.studio_waypoint_route as base
    import skeleton.ai.game_builder.studio_waypoint_risk as risk
    world = {
        "project_id": "original", "source_digest": DIGEST,
        "width": 6, "height": 5, "spawn": [1, 1], "target": [4, 3],
        "maps": [["######", "#....#", "#.##.#", "#....#", "######"]],
    }
    hazards = {
        "project_id": "original", "source_digest": DIGEST,
        "starting_health": 2, "hazard_damage": 1,
        "hazards_by_stage": [[[4, 1]]],
    }
    monkeypatch.setattr(base, "playable_world_source", lambda _: world)
    monkeypatch.setattr(risk, "playable_world_source", lambda _: world)
    monkeypatch.setattr(risk, "authored_hazards", lambda _: hazards)
    return {"original": True}, world, hazards


def plan(source, *, start=None, waypoints=None, hits=0):
    docs, _, _ = source
    return compile_waypoint_risk(
        docs, scene_index=0, start=[1, 1] if start is None else start,
        waypoints=[] if waypoints is None else waypoints,
        max_hazard_contacts=hits, authorized=True,
        expected_source_digest=DIGEST,
    )


def test_zero_contact_route_is_deterministic_and_replayable(source):
    receipt = plan(source)
    assert receipt["hazard_contact_count"] == 0
    assert receipt["remaining_health"] == 2
    assert receipt["collision_checked"] is True
    assert receipt["release_certified"] is False
    assert replay_waypoint_risk(
        source[0], receipt, authorized=True, expected_source_digest=DIGEST,
    ) == receipt
    assert b"default-src 'none'" in render_waypoint_risk_html(
        source[0], receipt, authorized=True, expected_source_digest=DIGEST,
    )


def test_risk_route_prefers_survival_over_shortest_path(source):
    # The direct eastern corridor crosses a hazard; a longer safe detour wins.
    receipt = plan(source, start=[3, 1], waypoints=[[4, 3]])
    assert receipt["hazard_contact_count"] == 0
    assert receipt["finish"] == [4, 3]


def test_contact_budget_is_respected_and_counted_per_entry(source):
    docs, world, hazards = source
    hazards["hazards_by_stage"][0] = [[1, 3], [4, 1]]
    receipt = plan(source, waypoints=[[1, 3]], hits=1)
    assert receipt["hazard_contacts"] == [[1, 3]]
    assert receipt["remaining_health"] == 1
    assert receipt["hazard_contact_count"] == 1
    with pytest.raises(StudioQuestError, match="survivable"):
        plan(source, waypoints=[[1, 3]], hits=0)


@pytest.mark.parametrize("hits", [-1, True, 17, 1.0, "1"])
def test_invalid_risk_budgets_fail_closed(source, hits):
    with pytest.raises(StudioQuestError):
        plan(source, hits=hits)


def test_fatal_budget_rejected(source):
    with pytest.raises(StudioQuestError, match="fatal"):
        plan(source, hits=2)


def test_source_drift_hazard_transplant_and_forgery_fail(source):
    receipt = plan(source)
    tampered = deepcopy(receipt)
    tampered["remaining_health"] = 9000
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_waypoint_risk(
            source[0], tampered, authorized=True, expected_source_digest=DIGEST,
        )
    source[2]["source_digest"] = "b" * 64
    with pytest.raises(StudioQuestError, match="custody"):
        plan(source)


def test_invalid_hazard_geometry_and_authority(source):
    source[2]["hazards_by_stage"][0] = [[0, 0]]
    with pytest.raises(StudioQuestError, match="invalid authored cell"):
        plan(source)
    with pytest.raises(PermissionError):
        compile_waypoint_risk(
            source[0], scene_index=0, start=[1, 1], waypoints=[],
            max_hazard_contacts=0, authorized=False,
            expected_source_digest=DIGEST,
        )


def test_private_publication_restore_and_tamper(source, tmp_path):
    receipt = plan(source)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert publish_waypoint_risk(
        source[0], receipt, private, authorized=True,
        expected_source_digest=DIGEST,
    )["file_write_performed"]
    assert restore_waypoint_risk(
        source[0], private, authorized=True,
        expected_source_digest=DIGEST,
    ) == receipt
    with pytest.raises(FileExistsError):
        publish_waypoint_risk(
            source[0], receipt, private, authorized=True,
            expected_source_digest=DIGEST,
        )
    target = private / FILENAME
    target.write_text('{"schema":"one","schema":"two"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_waypoint_risk(
            source[0], private, authorized=True,
            expected_source_digest=DIGEST,
        )
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_waypoint_risk(
            source[0], private, authorized=True,
            expected_source_digest=DIGEST,
        )


def test_cli_and_typed_jeeves_parity(source, tmp_path, monkeypatch, capsys):
    import scripts.studio_waypoint_risk_cli as cli
    import skeleton.ai.agents.jeeves.studio_waypoint_risk_tool as adapter
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    monkeypatch.setattr(cli, "read_blueprint", lambda _: source[0])
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: source[0])
    assert cli.main([
        "--project", "original", "--expected-source", DIGEST,
        "--waypoints", "[]", "--max-hazard-contacts", "0",
        "--publish", str(tmp_path), "--html-sha256",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["publication"]["file_write_performed"] is True
    assert cli.main([
        "--project", "original", "--expected-source", DIGEST,
        "--restore", str(tmp_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["risk_route"] == output["risk_route"]
    request = {
        "schema": adapter.REQUEST_SCHEMA, "project_id": "original",
        "expected_source_digest": DIGEST, "scene_index": 0,
        "start": [1, 1], "waypoints": [], "max_hazard_contacts": 0,
    }
    direct = adapter.execute_waypoint_risk_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_waypoint_risk", "arguments": request},
        authorized=True,
    )
    assert routed["result"] == direct
    assert direct["detail"] == output["risk_route"]
    assert routed["file_write_performed"] is False


def test_starting_on_hazard_requires_explicit_health_context(source):
    with pytest.raises(StudioQuestError, match="hazardous start"):
        plan(source, start=[4, 1])
