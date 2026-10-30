"""Complete source-to-real-2D-execution/asset verification regression."""
import json
from pathlib import Path
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_autoplay import simulate_complete_walk
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import replay_walk
from skeleton.ai.game_builder.studio_ecosystem_walk_review import review_walk_events
from skeleton.ai.game_builder.studio_ecosystem_encounters import (
    replay_hazard_health, authored_hazards,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_patrol import cast_patrols
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_offline_bundle import build_offline_studio_bundle
from skeleton.ai.game_builder.studio_ecosystem_offline_verify import verify_studio_bundle


@pytest.mark.parametrize("pid", [
    "studio_aerial_traversal_amber_highlands",
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_three_original_families_complete_real_2d_sandbox_physics(pid):
    docs=read_blueprint(pid)
    play=simulate_complete_walk(docs,authorized=True)
    state=replay_walk(docs,play["actions"],authorized=True)
    health=replay_hazard_health(docs,play["actions"],authorized=True)
    assert state.scene_index==3
    assert play["walk_session_sha256"]==state.digest
    assert health["remaining_health"]==authored_hazards(docs)["starting_health"]
    assert cast_patrols(docs)["actors"]
    browser={"schema":"skeleton.game_builder.offline_walk_events.v1",
             "project_id":pid,"source_digest":state.source_digest,
             "events":play["actions"],
             "external_evidence_verified":False,
             "native_genre_runtime_verified":False,
             "release_certified":False}
    inspected=review_walk_events(json.dumps(browser).encode(),docs,
                                  authorized=True)
    assert inspected["walk_session_digest"]==state.digest
    assert inspected["accepted_moves"]==state.accepted_moves
    assert inspected["scene_index"]==3
    assert not inspected["native_genre_runtime_verified"]


def test_production_v3_exports_original_media_and_extended_offline_game(tmp_path):
    root=tmp_path/"private";root.mkdir(mode=0o700)
    output=tmp_path/"output";output.mkdir(mode=0o700)
    pid="studio_arena_fighting_glacial_fjord"
    actor=StudioPortfolio(root,authorized=True).open(pid,authorized=True)
    result=build_offline_studio_bundle(actor.journal,actor.spool,output,
                                       walkable_story=True,authorized=True)
    verified=verify_studio_bundle(Path(result["output_dir"]),authorized=True)
    assert verified["files_verified"]==7
    payload=(output/pid/"walkable.html").read_bytes()
    assert b"actor.patrol_by_stage" in payload
    assert b"hazards_by_stage" in payload
    assert b"offline_npc_contacts.v1" in payload
    assert b"'unsafe-inline'" not in payload
    assert not verified["consumer_release_certified"]
