import pytest
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_offline_bundle import build_offline_studio_bundle
from skeleton.ai.game_builder.studio_ecosystem_census import audit_offline_portfolio
from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError

def test_portfolio_census_reports_exact_missing_and_verified_game_packages(tmp_path):
    work=tmp_path/"work";work.mkdir(mode=0o700)
    out=tmp_path/"out";out.mkdir(mode=0o700)
    ids=["studio_aerial_traversal_amber_highlands",
         "studio_arena_fighting_glacial_fjord"]
    supervisor=StudioPortfolio(work,authorized=True).open(ids[0],authorized=True)
    build_offline_studio_bundle(supervisor.journal,supervisor.spool,out,
                                walkable_story=True,authorized=True)
    partial=audit_offline_portfolio(out,project_ids=ids,expected_version=3,
                                    authorized=True)
    assert partial["valid_local_packages"]==1
    assert partial["missing_packages"]==1
    assert not partial["all_requested_valid"]
    assert not partial["consumer_release_certified"]
    repeated=audit_offline_portfolio(out,project_ids=ids,expected_version=3,
                                      authorized=True)
    assert partial["source_and_package_chain_sha256"]==repeated["source_and_package_chain_sha256"]
    with pytest.raises(StudioEcosystemError):
        audit_offline_portfolio(out,project_ids=[ids[0],ids[0]],authorized=True)
