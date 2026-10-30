import pytest
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_parallel import produce_parallel_games
from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError

def test_two_independent_walkable_projects_produce_in_one_admitted_wave(tmp_path):
    work=tmp_path/"work";work.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    ids=["studio_aerial_traversal_amber_highlands",
         "studio_arena_fighting_glacial_fjord"]
    report=produce_parallel_games(
        StudioPortfolio(work,authorized=True),out,
        project_ids=ids,working_set_bytes=1024,
        estimated_output_bytes=1024,walkable_story=True,authorized=True)
    assert report["all_projects_completed"]
    assert len(report["completed_projects"])==2
    assert all(x["files_verified"]==7 for x in report["completed_projects"])
    assert not report["consumer_release_certified"]
    assert len(list(out.glob("*/walkable.html")))==2

def test_parallel_requires_unique_registered_projects(tmp_path):
    work=tmp_path/"work";work.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    pid="studio_arena_fighting_glacial_fjord"
    with pytest.raises(StudioEcosystemError):
        produce_parallel_games(StudioPortfolio(work,authorized=True),out,
            project_ids=[pid,pid],working_set_bytes=1024,
            estimated_output_bytes=1024,authorized=True)
