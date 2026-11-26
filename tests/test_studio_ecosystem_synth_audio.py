from copy import deepcopy
from io import BytesIO
import wave
import pytest
from hashlib import sha256
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_synth_audio import render_cue_wav, cue_render_receipt
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("project,cue",[
 ("studio_aerial_traversal_amber_highlands","arrival"),
 ("studio_arena_fighting_glacial_fjord","ambient"),
])
def test_original_wav_is_deterministic_and_real_audio(project,cue):
    docs=read_blueprint(project)
    audio=render_cue_wav(docs,cue)
    with wave.open(BytesIO(audio),"rb") as stream:
        assert stream.getnframes()==48000
        assert stream.getnchannels()==1
        assert stream.getframerate()==16000
    assert audio==render_cue_wav(docs,cue)
    receipt=cue_render_receipt(docs,cue)
    assert receipt["wav_sha256"]==sha256(audio).hexdigest()
    assert receipt["pcm_audio_rendered"]
    assert not receipt["original_soundtrack_complete"]

def test_forged_cue_and_tempo_fail_closed():
    docs=deepcopy(read_blueprint("studio_arena_fighting_glacial_fjord"))
    with pytest.raises(StudioQuestError):
        render_cue_wav(docs,"not_an_authored_cue")
    docs["audio"]["sound_design"]["tempo_bpm"]=0
    with pytest.raises(StudioQuestError):
        render_cue_wav(docs,"ambient")
