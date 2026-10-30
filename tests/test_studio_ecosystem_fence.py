from copy import deepcopy
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_fence import assert_source_fence, pin_source_sections
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_journal_recovery_refuses_source_edit_even_when_quest_dag_unchanged(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    journal=WorkJournal(root,build_work_graph(docs),authorized=True)
    with pytest.raises(StudioQuestError):
        assert_source_fence(journal,docs,authorized=True)
    pin_source_sections(journal,docs,authorized=True)
    assert assert_source_fence(journal,docs,authorized=True)["section_count"]==8
    changed=deepcopy(docs)
    changed["narrative"]["premise"]="Rewritten but unapproved."
    with pytest.raises(StudioQuestError):
        assert_source_fence(journal,changed,authorized=True)
    with pytest.raises(PermissionError):
        assert_source_fence(journal,docs,authorized=False)

def test_full_section_change_is_fenced_even_when_quest_and_dag_unchanged(tmp_path):
    root=tmp_path/"secure"
    root.mkdir(mode=0o700)
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    journal=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(journal,docs,authorized=True)
    changed=deepcopy(docs)
    changed["visual"]["art_direction"]["palette"][0]="#FFFFFF"
    with pytest.raises(StudioQuestError):
        assert_source_fence(journal,changed,authorized=True)
    with pytest.raises(StudioQuestError):
        pin_source_sections(journal,changed,authorized=True)
