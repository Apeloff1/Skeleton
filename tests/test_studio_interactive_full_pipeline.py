"""End-state local proof across V1, V2, V3, live walking and real browser replay."""
import json
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_offline_bundle import build_offline_studio_bundle
from skeleton.ai.game_builder.studio_ecosystem_offline_verify import verify_studio_bundle
from skeleton.ai.game_builder.studio_ecosystem_story_html import story_source
from skeleton.ai.game_builder.studio_ecosystem_story_review import inspect_browser_story_receipt
from skeleton.ai.game_builder.studio_ecosystem_walkable import (
    playable_world_source,render_playable_world_html,_reachable,
)
from skeleton.ai.game_builder.studio_ecosystem_census import audit_offline_portfolio
from skeleton.ai.game_builder.studio_ecosystem_parallel import produce_parallel_games
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def test_registered_real_source_produces_three_backwards_compatible_game_variants(tmp_path):
    private=tmp_path/"work";private.mkdir(mode=0o700)
    output=tmp_path/"output";output.mkdir(mode=0o700)
    portfolio=StudioPortfolio(private,authorized=True)
    projects=[
        ("studio_aerial_traversal_amber_highlands",{},5),
        ("studio_puzzle_expedition_copper_mesa",{"interactive_story":True},6),
        ("studio_arena_fighting_glacial_fjord",{"walkable_story":True},7),
    ]
    ids=[]
    for pid,kwargs,expected_files in projects:
        ids.append(pid)
        supervisor=portfolio.open(pid,authorized=True)
        result=build_offline_studio_bundle(supervisor.journal,supervisor.spool,
                                           output,authorized=True,**kwargs)
        verification=verify_studio_bundle(output/pid,authorized=True)
        assert verification["files_verified"]==expected_files
        assert verification["local_bundle_integrity_verified"]
        assert not verification["native_gameplay_qualified"]
        assert not result["consumer_release_certified"]
    audit=audit_offline_portfolio(output,project_ids=ids,authorized=True)
    assert audit["all_requested_valid"]
    assert audit["valid_local_packages"]==3
    assert not audit["consumer_release_certified"]
    (output/ids[2]/"walkable.html").write_bytes(b"corrupt")
    assert audit_offline_portfolio(output,project_ids=ids,
                                    authorized=True)["rejected_packages"]==1


def test_walkable_world_actions_can_be_replayed_by_python_without_fake_proof():
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    scene=playable_world_source(docs)
    source=story_source(docs)
    assert len(scene["maps"])==3
    assert all(_reachable(rows) for rows in scene["maps"])
    html=render_playable_world_html(docs)
    assert b"transcriptReceipt()" in html
    first=source["stages"][0]
    payload={"schema":"skeleton.game_builder.offline_story_choices.v1",
             "project_id":source["project_id"],
             "source_digest":source["source_digest"],
             "choices":[[first["id"],first["alternatives"][0]]],
             "external_evidence_verified":False,
             "native_genre_runtime_verified":False,
             "release_certified":False}
    report=inspect_browser_story_receipt(json.dumps(payload).encode(),
                                          docs,authorized=True)
    assert report["completed_stages"]==[first["id"]]
    assert not report["release_certified"]
    payload["choices"]=[["ratify","residents_vote"]]
    with pytest.raises(StudioQuestError):
        inspect_browser_story_receipt(json.dumps(payload).encode(),docs,authorized=True)
