"""Integrated end-to-end studio source/quest/production checks on both families."""
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_manifest import source_manifest,verify_source_manifest
from skeleton.ai.game_builder.studio_ecosystem_quest import start_quest,verify_quest_session
from skeleton.ai.game_builder.studio_ecosystem_scene import scene_catalog
from skeleton.ai.game_builder.studio_ecosystem_turn import apply_story_turn
from skeleton.ai.game_builder.studio_ecosystem_social import compile_factions, replay_factions
from skeleton.ai.game_builder.studio_ecosystem_resources import start_resources,resource_receipt
from skeleton.ai.game_builder.studio_ecosystem_save import encode_quest_save,restore_quest_save
from skeleton.ai.game_builder.studio_ecosystem_endings import ending_obligations
from skeleton.ai.game_builder.studio_ecosystem_audio import compile_cue_sheet
from skeleton.ai.game_builder.studio_ecosystem_assets import planned_assets
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph,ready_work
from skeleton.ai.game_builder.studio_ecosystem_frame import production_frame


@pytest.mark.parametrize("project",[
    "studio_aerial_traversal_amber_highlands",
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_real_source_to_three_turn_replay_to_production_hold(project):
    docs=read_blueprint(project)
    manifest=source_manifest(docs)
    verify_source_manifest(manifest,docs)
    scenes=scene_catalog(docs)
    program=docs["quest"].get("stage_graph") or docs["quest"]["stages"]
    session=start_quest(docs,authorized=True)
    for scene,stage in zip(scenes,program,strict=True):
        assert stage["id"]==scene["quest_stage"]
        turn=apply_story_turn(docs,session,scene_id=scene["scene_id"],
            object_id=scene["objects"][0],stage=stage["id"],
            alternative=stage["alternatives"][0],authorized=True)
        assert turn.previous_quest_digest==session.digest
        assert not turn.intent["object_interaction_performed"]
        session=turn.quest
    verify_quest_session(session,docs)
    saved=encode_quest_save(session,docs,authorized=True)
    assert restore_quest_save(saved,docs,authorized=True)==session
    assert len(session.completed)==3
    decision=compile_factions(docs).decisions[0][0]
    social=replay_factions(docs,[decision],authorized=True)
    assert social["events"] and not social["release_certified"]
    budget=resource_receipt(start_resources(docs,starting_quantity=4,
                                             authorized=True),docs)
    assert budget["balances"]["reserve"]==4
    assert compile_cue_sheet(docs)["cues"]
    assert planned_assets(docs)["jobs"]
    g=build_work_graph(docs)
    assert ready_work(g,[],authorized=True)["ready_for_operator_review"]==["source-canon"]
    assert ending_obligations(docs,session)["endings"]
    frame=production_frame(docs,session,authorized=True)
    assert frame["manifest"]==manifest
    assert not frame["release_requirements"]["release_certified"]
    assert not frame["native_genre_runtime_verified"]
    assert not frame["release_certified"]
