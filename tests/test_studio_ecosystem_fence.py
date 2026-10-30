from copy import deepcopy
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_fence import assert_source_fence
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_journal_recovery_refuses_source_edit_even_when_quest_dag_unchanged(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    journal=WorkJournal(root,build_work_graph(docs),authorized=True)
    assert assert_source_fence(journal,docs,authorized=True)["section_count"]==8
    changed=deepcopy(docs)
    changed["narrative"]["premise"]="Rewritten but unapproved."
    with pytest.raises(StudioQuestError):
        assert_source_fence(journal,changed,authorized=True)
    with pytest.raises(PermissionError):
        assert_source_fence(journal,docs,authorized=False)
