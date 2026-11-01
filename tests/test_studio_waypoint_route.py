"""Focused deterministic and adversarial waypoint-route contracts."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_waypoint_route import (
    FILENAME, compile_waypoint_route, replay_waypoint_route,
    render_waypoint_route_html, publish_waypoint_route, restore_waypoint_route,
)


@pytest.fixture
def source(monkeypatch):
    import skeleton.ai.game_builder.studio_waypoint_route as mod
    world = {
        "project_id": "original",
        "source_digest": "a" * 64,
        "width": 6, "height": 5, "spawn": [1, 1], "target": [4, 3],
        "maps": [
            ["######", "#....#", "#.##.#", "#....#", "######"],
        ],
    }
    monkeypatch.setattr(mod, "playable_world_source", lambda docs: world)
    return {"original": True}


def route(source, waypoints=None):
    return compile_waypoint_route(
        source, scene_index=0, start=[1, 1],
        waypoints=[] if waypoints is None else waypoints,
        authorized=True, expected_source_digest="a" * 64,
    )


def test_shortest_interaction_route_and_replay(source):
    receipt = route(source)
    assert receipt["finish"] in ([4, 3], [3, 3], [4, 2])
    assert receipt["accepted_steps"] == len(receipt["directions"])
    assert receipt["collision_checked"] is True
    assert receipt["release_certified"] is False
    assert replay_waypoint_route(
        source, receipt, authorized=True, expected_source_digest="a" * 64,
    ) == receipt
    assert b"default-src 'none'" in render_waypoint_route_html(
        source, receipt, authorized=True, expected_source_digest="a" * 64,
    )


def test_waypoint_enforces_authored_detour(source):
    receipt = route(source, [[1, 3], [4, 3]])
    assert len(receipt["legs"]) == 3
    assert receipt["legs"][0]["finish"] == [1, 3]
    assert receipt["legs"][1]["finish"] == [4, 3]
    assert receipt["legs"][2]["accepted_steps"] == 0
    assert receipt["accepted_steps"] >= 5


@pytest.mark.parametrize("waypoints", [
    [[2, 2]], [[0, 0]], [[1, 3], [1, 3]], [[True, 1]],
    [["1", 1]], [[1, 1, 1]], [[1, 3]] * 9,
])
def test_invalid_waypoints_fail_closed(source, waypoints):
    with pytest.raises(StudioQuestError):
        route(source, waypoints)


def test_unreachable_waypoint_rejected(source, monkeypatch):
    import skeleton.ai.game_builder.studio_waypoint_route as mod
    world = mod.playable_world_source(source)
    broken = deepcopy(world)
    broken["maps"][0] = [
        "######", "#.#..#", "###..#", "#....#", "######",
    ]
    monkeypatch.setattr(mod, "playable_world_source", lambda docs: broken)
    with pytest.raises(StudioQuestError, match="unreachable"):
        route(source, [[4, 3]])


def test_stale_source_tamper_and_authority_fail(source, monkeypatch):
    receipt = route(source)
    forged = deepcopy(receipt)
    forged["directions"] = ["up"]
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_waypoint_route(
            source, forged, authorized=True, expected_source_digest="a" * 64,
        )
    with pytest.raises(StudioQuestError, match="stale"):
        compile_waypoint_route(
            source, scene_index=0, start=[1, 1], waypoints=[],
            authorized=True, expected_source_digest="b" * 64,
        )
    with pytest.raises(PermissionError):
        compile_waypoint_route(
            source, scene_index=0, start=[1, 1], waypoints=[],
            authorized=False, expected_source_digest="a" * 64,
        )


def test_private_persistence_and_import_security(source, tmp_path):
    receipt = route(source, [[1, 3]])
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert publish_waypoint_route(
        source, receipt, private, authorized=True,
        expected_source_digest="a" * 64,
    )["file_write_performed"]
    assert restore_waypoint_route(
        source, private, authorized=True,
        expected_source_digest="a" * 64,
    ) == receipt
    with pytest.raises(FileExistsError):
        publish_waypoint_route(
            source, receipt, private, authorized=True,
            expected_source_digest="a" * 64,
        )
    target = private / FILENAME
    target.write_text('{"schema":"one","schema":"two"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_waypoint_route(
            source, private, authorized=True,
            expected_source_digest="a" * 64,
        )
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_waypoint_route(
            source, private, authorized=True,
            expected_source_digest="a" * 64,
        )


def test_cli_and_typed_jeeves_route(source, tmp_path, monkeypatch, capsys):
    from scripts.studio_waypoint_route_cli import main
    from skeleton.ai.agents.jeeves.studio_waypoint_route_tool import (
        REQUEST_SCHEMA, execute_waypoint_route_tool,
    )
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    import skeleton.ai.agents.jeeves.studio_waypoint_route_tool as adapter
    import scripts.studio_waypoint_route_cli as cli
    monkeypatch.setattr(adapter, "read_blueprint", lambda project: source)
    monkeypatch.setattr(cli, "read_blueprint", lambda project: source)
    assert main([
        "--project", "original", "--expected-source", "a" * 64,
        "--waypoints", "[[1,3]]", "--publish", str(tmp_path),
        "--html-sha256",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["route"]["waypoints"] == [[1, 3]]
    assert main([
        "--project", "original", "--expected-source", "a" * 64,
        "--restore", str(tmp_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["route"] == output["route"]
    request = {
        "schema": REQUEST_SCHEMA, "project_id": "original",
        "expected_source_digest": "a" * 64, "scene_index": 0,
        "start": [1, 1], "waypoints": [[1, 3]],
    }
    direct = execute_waypoint_route_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_waypoint_route", "arguments": request},
        authorized=True,
    )
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    assert direct["detail"] == output["route"]
