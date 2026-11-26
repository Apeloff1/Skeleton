import pytest
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_resume_batch import resume_catalog_preview_batch
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_second_pass_reuses_only_full_verified_source_bound_packages(tmp_path):
    work=tmp_path/"work"
    work.mkdir(mode=0o700)
    out=tmp_path/"output"
    out.mkdir(mode=0o700)
    owner=StudioPortfolio(work,authorized=True)
    a="studio_aerial_traversal_amber_highlands"
    b="studio_arena_fighting_glacial_fjord"
    first=resume_catalog_preview_batch(owner,out,project_ids=[a],
        working_set_bytes=1024,estimated_output_bytes=1024,authorized=True)
    assert first["built_now"]==[a]
    second=resume_catalog_preview_batch(owner,out,project_ids=[a,b],
        working_set_bytes=1024,estimated_output_bytes=1024,authorized=True)
    assert second["reused_verified"]==[a]
    assert second["built_now"]==[b]
    assert second["all_projects_complete"] is True
    (out/a/"studio.html").write_text("corrupt")
    with pytest.raises(StudioQuestError):
        resume_catalog_preview_batch(owner,out,project_ids=[a],
            working_set_bytes=1024,estimated_output_bytes=1024,authorized=True)

def test_resume_refuses_to_relabel_old_v1_package_as_walkable_v3(tmp_path):
    work=tmp_path/"work";work.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    owner=StudioPortfolio(work,authorized=True)
    pid="studio_aerial_traversal_amber_highlands"
    resume_catalog_preview_batch(owner,out,project_ids=[pid],
        working_set_bytes=1024,estimated_output_bytes=1024,authorized=True)
    with pytest.raises(StudioQuestError):
        resume_catalog_preview_batch(owner,out,project_ids=[pid],
            working_set_bytes=1024,estimated_output_bytes=1024,
            walkable_story=True,authorized=True)
