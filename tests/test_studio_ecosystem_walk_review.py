import json
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_navigation import shortest_scene_route
from skeleton.ai.game_builder.studio_ecosystem_walk_review import review_walk_events
from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def _payload(pid, actions, docs):
    world = playable_world_source(docs)
    return {"schema": "skeleton.game_builder.offline_walk_events.v1",
            "project_id": pid, "source_digest": world["source_digest"],
            "events": actions, "external_evidence_verified": False,
            "native_genre_runtime_verified": False, "release_certified": False}


def test_replay_real_browser_navigation_with_marker_interaction():
    pid = "studio_arena_fighting_glacial_fjord"
    docs = read_blueprint(pid)
    route = shortest_scene_route(docs, scene_index=0, authorized=True)
    option = playable_world_source(docs)["stages"][0]["alternatives"][0]
    actions = [["move", direction] for direction in route["directions"]]
    actions.append(["choose", option])
    report = review_walk_events(json.dumps(_payload(pid, actions, docs)).encode(),
                                docs, authorized=True)
    assert report["scene_index"] == 1
    assert report["accepted_moves"] == len(route["directions"])
    assert not report["external_input_authenticity_verified"]
    actions[0] = ["move", "left"]
    with pytest.raises(StudioQuestError):
        review_walk_events(json.dumps(_payload(pid, actions, docs)).encode(),
                           docs, authorized=True)


def test_replay_rejects_forged_release_or_repeated_json_keys():
    docs = read_blueprint("studio_arena_fighting_glacial_fjord")
    forged = _payload("studio_arena_fighting_glacial_fjord", [], docs)
    forged["release_certified"] = True
    with pytest.raises(StudioQuestError):
        review_walk_events(json.dumps(forged).encode(), docs, authorized=True)
    with pytest.raises(StudioQuestError):
        review_walk_events(b'{"project_id":"a","project_id":"b"}',
                           docs, authorized=True)
