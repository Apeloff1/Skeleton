import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_fence import pin_source_sections
from skeleton.ai.game_builder.studio_ecosystem_quest import start_quest,step_quest,StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_checkpoint_store import persist_quest_checkpoint,resume_quest_checkpoint

def test_quest_replay_checkpoint_survives_reopen(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    docs=read_blueprint("studio_aerial_traversal_amber_highlands")
    j=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(j,docs,authorized=True)
    spool=ArtifactSpool(root,authorized=True)
    start=start_quest(docs,authorized=True)
    continued=step_quest(start,docs,stage="arrival",alternative="inspect_markers",
                          authorized=True)
    checkpoint=persist_quest_checkpoint(j,spool,continued,authorized=True)
    opened=WorkJournal(root,build_work_graph(docs),authorized=True)
    resumed=resume_quest_checkpoint(opened,ArtifactSpool(root,authorized=True),
                                    checkpoint=checkpoint,authorized=True)
    assert resumed==continued
    invalid={**checkpoint,"session_digest":"0"*64}
    with pytest.raises(StudioQuestError):
        resume_quest_checkpoint(opened,spool,checkpoint=invalid,authorized=True)
    assert not checkpoint["native_game_save_qualified"]
