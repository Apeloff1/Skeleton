from copy import deepcopy
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_audio import compile_cue_sheet, cues_for_event
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid,trigger",[
 ("studio_aerial_traversal_amber_highlands","landslides"),
 ("studio_puzzle_expedition_copper_mesa","arrival"),
 ("studio_arena_fighting_glacial_fjord","duel"),
])
def test_real_authored_cue_formats(pid,trigger):
    docs=read_blueprint(pid)
    sheet=compile_cue_sheet(docs)
    assert len(sheet["cues"])>=3
    result=cues_for_event(docs,event=trigger,authorized=True)
    assert result["matched_cues"]
    assert not result["audio_actually_played"]
    assert sheet["release_certified"] is False
    with pytest.raises(PermissionError):
        cues_for_event(docs,event=trigger,authorized=False)

def test_duplicate_cue_identity_is_rejected():
    docs=deepcopy(read_blueprint("studio_arena_fighting_glacial_fjord"))
    docs["audio"]["sound_layers"][1]["id"]=docs["audio"]["sound_layers"][0]["id"]
    with pytest.raises(StudioQuestError):
        compile_cue_sheet(docs)
