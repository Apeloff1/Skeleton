"""Real scene exploration, fog-of-war, route, replay and export acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_atlas import (
    cli, compare_atlases, export_atlas, import_atlas,
    inspect_atlas, route_known,
)
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, original_demo, simulate,
)


def _play():
    world, actions = original_demo()
    return world, actions, simulate(world, actions)


def test_atlas_only_shows_visited_rooms_and_real_inventory() -> None:
    world, actions, session = _play()
    atlas = inspect_atlas(simulate(world, actions[:1]))
    assert atlas["known_scene_count"] == 1
    assert atlas["current_scene"] == "quay"
    assert atlas["inventory"] == ["brass_key"]
    assert [room["scene_id"] for room in atlas["rooms"]] == ["quay"]
    assert all(not edge["destination_discovered"] for edge in atlas["rooms"][0]["exits"])
    assert atlas["history"][0]["new_items"] == ["brass_key"]


def test_explored_atlas_has_canonical_history_and_ending() -> None:
    _, _, session = _play()
    atlas = inspect_atlas(session)
    assert atlas["phase"] == "won"
    assert atlas["ending"] == "victory"
    assert atlas["known_scene_count"] == 3
    assert [step["to"] for step in atlas["history"]] == [
        "quay", "gate", "sanctuary",
    ]
    assert atlas["state_digest"] == session["state_digest"]


def test_route_to_discovered_room_respects_held_keys() -> None:
    world, actions, _ = _play()
    world["scenes"][1]["exits"].append({
        "id": "south", "to": "quay", "requires_item": None,
    })
    partial = simulate(world, actions[:2])
    result = route_known(partial, "quay")
    assert result["reachable"] is True
    assert result["steps"] == [{
        "kind": "travel", "exit_id": "south", "from": "gate", "to": "quay",
    }]
    assert result["source_digest"] == partial["source_digest"]


def test_unseen_destination_is_not_leaked_by_route() -> None:
    world, actions, _ = _play()
    session = simulate(world, actions[:1])
    with pytest.raises(SceneTravelError, match="not been discovered"):
        route_known(session, "sanctuary")
    with pytest.raises(SceneTravelError, match="invalid target"):
        route_known(session, "../secrets")


def test_route_to_current_room_is_zero_step() -> None:
    world, actions, _ = _play()
    session = simulate(world, actions[:1])
    result = route_known(session, "quay")
    assert result["reachable"] is True
    assert result["steps"] == []


def test_compare_identical_prefix_and_divergent_real_playthroughs() -> None:
    world, actions, full = _play()
    partial = simulate(world, actions[:1])
    failure = simulate(world, [{"kind": "travel", "exit_id": "down"}])
    assert compare_atlases(full, copy.deepcopy(full))["relationship"] == "identical"
    assert compare_atlases(partial, full)["relationship"] == "prefix"
    diff = compare_atlases(full, failure)
    assert diff["relationship"] == "divergent"
    assert diff["common_turns"] == 0


def test_atlas_bundle_roundtrips_and_replays_canonical_state() -> None:
    _, _, session = _play()
    bundle = export_atlas(session)
    assert import_atlas(json.loads(json.dumps(bundle))) == session
    assert bundle["source_digest"] == session["source_digest"]


def test_forged_map_even_with_recomputed_checksum_is_rejected() -> None:
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    _, _, session = _play()
    bundle = export_atlas(session)
    bundle["atlas"]["inventory"].append("master_key")
    bundle["checksum"] = dig({
        key: value for key, value in bundle.items() if key != "checksum"
    })
    with pytest.raises(SceneTravelError, match="replay mismatch"):
        import_atlas(bundle)


def test_forged_session_receipt_is_rejected() -> None:
    _, _, session = _play()
    bundle = export_atlas(session)
    bundle["session"]["state"]["scene_id"] = "sinkhole"
    with pytest.raises(SceneTravelError):
        import_atlas(bundle)


def test_bundle_rejects_unknown_fields_and_invalid_checksum() -> None:
    _, _, session = _play()
    bundle = export_atlas(session)
    bundle["extra"] = "injection"
    with pytest.raises(SceneTravelError):
        import_atlas(bundle)
    bundle = export_atlas(session)
    bundle["checksum"] = "not-a-hash"
    with pytest.raises(SceneTravelError):
        import_atlas(bundle)


def test_compare_rejects_different_source() -> None:
    world, actions, full = _play()
    world["world_id"] = "other_world"
    changed = simulate(world, actions)
    with pytest.raises(SceneTravelError, match="identical authored"):
        compare_atlases(full, changed)


def test_installed_cli_demo_and_import(capsys) -> None:
    from skeleton.__main__ import main
    assert main(["scene-atlas", "demo"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert bundle["atlas"]["ending"] == "victory"
    assert cli(["verify", "--bundle-json", json.dumps(bundle)]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored == bundle["session"]


def test_cli_route_and_invalid_json(capsys) -> None:
    world, actions, _ = _play()
    session = simulate(world, actions[:1])
    assert cli(["route", "--session-json", json.dumps(session),
                "--target-scene", "quay"]) == 0
    assert json.loads(capsys.readouterr().out)["steps"] == []
    assert cli(["inspect", "--session-json", "{"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_route_reports_unreachable_without_inventing_reverse_exit() -> None:
    world, actions, _ = _play()
    session = simulate(world, actions[:2])
    result = route_known(session, "quay")
    assert result["reachable"] is False
    assert result["steps"] is None


def test_cli_rejects_duplicate_and_nonfinite_json(capsys) -> None:
    assert cli(["inspect", "--session-json", '{"x":1,"x":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert cli(["inspect", "--session-json", "NaN"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
