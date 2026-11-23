import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import start_walk,walk_action
from skeleton.ai.game_builder.studio_ecosystem_walk_checkpoint import (
    persist_walk_checkpoint,resume_walk_checkpoint,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def test_real_physics_progress_survives_reopen_and_blocks_forged_digests(tmp_path):
    root=tmp_path/"private";root.mkdir(mode=0o700)
    pid="studio_arena_fighting_glacial_fjord"
    first=StudioPortfolio(root,authorized=True).open(pid,authorized=True)
    documents=read_blueprint(pid)
    session=walk_action(start_walk(documents,authorized=True),documents,
                        action="move",value="right",authorized=True)
    checkpoint=persist_walk_checkpoint(first.journal,first.spool,session,
                                        authorized=True)
    reopened=StudioPortfolio(root,authorized=True).open(pid,authorized=True)
    restored=resume_walk_checkpoint(reopened.journal,reopened.spool,
                                    checkpoint=checkpoint,authorized=True)
    assert restored==session
    assert restored.position==(2,1)
    forged={**checkpoint,"walk_session_digest":"0"*64}
    with pytest.raises(StudioQuestError):
        resume_walk_checkpoint(reopened.journal,reopened.spool,
                               checkpoint=forged,authorized=True)
    assert checkpoint["release_certified"] is False
