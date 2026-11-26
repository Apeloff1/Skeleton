import json
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import start_quest, step_quest, StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_save import encode_quest_save, restore_quest_save

@pytest.mark.parametrize("project", ["studio_aerial_traversal_amber_highlands",
                                    "studio_arena_fighting_glacial_fjord"])
def test_source_bound_quest_restore_and_canonical_protection(project):
    docs=read_blueprint(project)
    session=start_quest(docs,authorized=True)
    stage=(docs["quest"].get("stage_graph") or docs["quest"]["stages"])[0]
    session=step_quest(session,docs,stage=stage["id"],
                       alternative=stage["alternatives"][0],authorized=True)
    blob=encode_quest_save(session,docs,authorized=True)
    assert restore_quest_save(blob,docs,authorized=True)==session
    altered=json.loads(blob)
    altered["session_digest"]="0"*64
    with pytest.raises(StudioQuestError):
        restore_quest_save((json.dumps(altered)+"\n").encode(),docs,authorized=True)
    with pytest.raises(StudioQuestError):
        restore_quest_save(b'{"schema":1,"schema":2}\n',docs,authorized=True)
    with pytest.raises(PermissionError):
        restore_quest_save(blob,docs,authorized=False)
