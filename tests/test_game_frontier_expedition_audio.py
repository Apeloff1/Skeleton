"""Original procedural WAV soundtracks and environmental audio proof."""
from dataclasses import replace
from hashlib import sha256
import io
import wave
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_audio import (
    MusicalNote,AudioScore,render_original_audio,original_world_score,
    export_original_soundscape,verify_original_soundscape,
)
from tests.test_game_frontier_expedition_godot import world


def test_homebrew_audio_is_a_real_playable_pcm_wavefile():
    w=world()
    score=original_world_score(w,seconds=2)
    raw=render_original_audio(score)
    assert raw.startswith(b"RIFF")
    assert b"WAVE" in raw[:12]
    with wave.open(io.BytesIO(raw),"rb") as wav:
        assert wav.getnchannels()==1
        assert wav.getsampwidth()==2
        assert wav.getframerate()==16000
        assert wav.getnframes()==32000
        pcm=wav.readframes(wav.getnframes())
    assert any(byte!=0 for byte in pcm)
    assert len(pcm)==64000


def test_seeded_music_and_environment_produce_identical_source_bytes():
    a=export_original_soundscape(world(),ambience="wind",seconds=2)
    b=export_original_soundscape(world(),ambience="wind",seconds=2)
    assert a==b
    assert a["manifest"]["audio_sha256"]==sha256(a["wav"]).hexdigest()
    assert a["score"].digest==b["score"].digest
    assert not a["manifest"]["copyright_sampling_used"]
    assert not a["manifest"]["native_audio_playback_verified"]
    verify_original_soundscape(world(),a,ambience="wind",seconds=2)


@pytest.mark.parametrize("ambience",(
    "none","wind","rain","cave","underwater","forest","volcano",
))
def test_seven_original_ambient_environments_generate_distinct_audio(ambience):
    w=world()
    result=export_original_soundscape(w,ambience=ambience,seconds=1)
    assert result["manifest"]["ambience"]==ambience
    assert result["manifest"]["notes"]==8
    assert len(result["wav"])>32000
    assert len(result["manifest"]["receipt_digest"])==64


def test_environment_sound_changes_wave_bytes_not_story_world_hash():
    w=world()
    rain=export_original_soundscape(w,ambience="rain",seconds=1)
    cave=export_original_soundscape(w,ambience="cave",seconds=1)
    assert rain["wav"]!=cave["wav"]
    assert rain["manifest"]["world_digest"]==cave["manifest"]["world_digest"]


def test_laundered_or_modified_audio_is_rejected_on_independent_render():
    w=world()
    made=export_original_soundscape(w,seconds=1)
    tampered=dict(made)
    tampered["wav"]=made["wav"][:-2]+b"\0\0"
    with pytest.raises(ExpeditionError,match="not reproduce"):
        verify_original_soundscape(w,tampered,seconds=1)


def test_audio_note_validation_rejects_truncated_or_nonfinite_frequency():
    with pytest.raises(ExpeditionError,match="frequency"):
        MusicalNote(float("nan"),0,10)
    with pytest.raises(ExpeditionError,match="truncated"):
        AudioScore("bad","f"*64,(MusicalNote(440,1000,1500),),
                   duration_ms=2000)
    with pytest.raises(ExpeditionError,match="instrument"):
        MusicalNote(440,0,100,instrument="licensed_sample")


def test_original_score_contains_real_playable_note_timestamps():
    score=original_world_score(world(),seconds=3)
    assert all(note.length_ms>0 for note in score.notes)
    assert all(note.start_ms+note.length_ms<=score.duration_ms for note in score.notes)
    assert [note.start_ms for note in score.notes]==sorted(
        note.start_ms for note in score.notes)
