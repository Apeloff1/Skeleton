"""Generate short original PCM/WAV ambience from authored studio music cues.

A deterministic local sound-design demonstrator: synthesized original tones,
rhythm and air, without borrowed audio, voice imitation, external services,
network files or claims of completed score/mixer certification.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import math
import struct
from typing import Any, Mapping
import wave

from .studio_ecosystem_audio import compile_cue_sheet
from .studio_ecosystem_quest import StudioQuestError

RATE=16000
SECONDS=3
FRAMES=RATE*SECONDS


def _tempo(documents: Mapping[str, Any]) -> int:
    audio=documents.get("audio")
    if not isinstance(audio, dict):
        raise StudioQuestError("missing authored audio")
    sources=[audio.get(k) for k in ("composition","soundscape","sound_design")]
    config=next((s for s in sources if isinstance(s,dict)),None)
    if config is None:
        raise StudioQuestError("no original music direction")
    tempo=config.get("tempo_bpm",config.get("tempo"))
    if type(tempo) is not int or not 35<=tempo<=240:
        raise StudioQuestError("invalid authored musical tempo")
    return tempo


def render_cue_wav(documents: Mapping[str, Any], cue_id: str) -> bytes:
    sheet=compile_cue_sheet(documents)
    if not isinstance(cue_id,str) or cue_id not in {
        row["cue_id"] for row in sheet["cues"]
    }:
        raise StudioQuestError("cue not registered in original audio source")
    tempo=_tempo(documents)
    digest=sha256((sheet["source_digest"]+cue_id).encode("utf-8")).digest()
    tonic=110.0*2**((digest[0]%12)/12)
    fifth=tonic*1.498307
    upper=tonic*2
    phase0=(digest[2]/255)*math.tau
    beat_seconds=60.0/tempo
    frames=bytearray()
    for index in range(FRAMES):
        time=index/RATE
        envelope=min(1.0,time*7.0)*min(1.0,(SECONDS-time)*2.6)
        chord=(math.sin(math.tau*tonic*time+phase0)
               +0.43*math.sin(math.tau*fifth*time)
               +0.16*math.sin(math.tau*upper*time))/1.59
        rhythmic_phase=(time%beat_seconds)/beat_seconds
        pulse=math.exp(-rhythmic_phase*17.0)
        click=math.sin(math.tau*(tonic*4.0)*time)*pulse*0.18
        breeze=math.sin(math.tau*0.43*time)*math.sin(math.tau*(tonic/2)*time)*0.08
        sample=max(-0.95,min(0.95,envelope*(chord*0.21+click+breeze)))
        frames.extend(struct.pack("<h",round(sample*32767)))
    result=BytesIO()
    with wave.open(result,"wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(frames)
    return result.getvalue()


def cue_render_receipt(documents: Mapping[str, Any], cue_id: str) -> dict[str, object]:
    payload=render_cue_wav(documents,cue_id)
    sheet=compile_cue_sheet(documents)
    return {"schema":"skeleton.game_builder.original_audio_preview.v1",
            "project_id":sheet["project_id"],"cue_id":cue_id,
            "wav_sha256":sha256(payload).hexdigest(),
            "wav_bytes":len(payload),"sample_rate":RATE,
            "duration_seconds":SECONDS,
            "pcm_audio_rendered":True,
            "original_soundtrack_complete":False,
            "voice_performance_produced":False,
            "rights_independently_qualified":False,"release_certified":False}
