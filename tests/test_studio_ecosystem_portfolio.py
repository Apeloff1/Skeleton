import pytest
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError

def test_project_journals_are_namespaced_not_shared(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    owner=StudioPortfolio(root,authorized=True)
    first="studio_aerial_traversal_amber_highlands"
    second="studio_arena_fighting_glacial_fjord"
    a=owner.open(first,authorized=True)
    b=owner.open(second,authorized=True)
    assert a.journal.path!=b.journal.path
    assert a.journal.project!=b.journal.project
    assert len(list(owner.inspect_registered_workspaces()))==2
    with pytest.raises(StudioEcosystemError):
        owner.open("../untrusted",authorized=True)
    with pytest.raises(PermissionError):
        owner.open(first,authorized=False)
