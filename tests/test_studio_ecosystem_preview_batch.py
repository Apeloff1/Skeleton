import pytest
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_preview_batch import build_catalog_preview_batch
from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError

def test_two_registered_original_projects_produce_separate_packages(tmp_path):
    private=tmp_path/"private"
    private.mkdir(mode=0o700)
    output=tmp_path/"outputs"
    output.mkdir(mode=0o700)
    portfolio=StudioPortfolio(private,authorized=True)
    ids=["studio_aerial_traversal_amber_highlands","studio_arena_fighting_glacial_fjord"]
    report=build_catalog_preview_batch(portfolio,output,project_ids=ids,
                                       working_set_bytes=1024,
                                       estimated_output_bytes=1024,authorized=True)
    assert report["completed_projects"]==2
    assert report["all_projects_completed"]
    assert len(list(output.glob("*/manifest.json")))==2
    assert not report["consumer_release_certified"]
    with pytest.raises(StudioEcosystemError):
        build_catalog_preview_batch(portfolio,output,project_ids=[ids[0],ids[0]],
                                     working_set_bytes=1024,estimated_output_bytes=1024,
                                     authorized=True)

def test_successful_batch_receipts_have_measured_not_estimated_metrics(tmp_path):
    private=tmp_path/"private"
    private.mkdir(mode=0o700)
    output=tmp_path/"output"
    output.mkdir(mode=0o700)
    report=build_catalog_preview_batch(
        StudioPortfolio(private,authorized=True),output,
        project_ids=["studio_aerial_traversal_amber_highlands"],
        working_set_bytes=1024,estimated_output_bytes=1024,authorized=True)
    first=report["receipts"][0]
    assert first["elapsed_monotonic_ns"]>0
    assert isinstance(first["measured_disk_change_bytes"],int)
    assert first["target_genre_qualified"] is False
