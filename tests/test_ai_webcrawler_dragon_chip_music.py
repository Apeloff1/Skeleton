"""Genre-adaptive original chip synthesis and native Game Boy APU correctness."""
from __future__ import annotations
from hashlib import sha256
import json
import pytest

from skeleton.ai.webcrawler.dragon_chip_music import compose,emit_score_header
from skeleton.ai.webcrawler.dragon_game_blueprints import GAME_MODES
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_gb_sound import enrich_native_gb_sound


def _build(target,style):
    return render_native_project(
        title="Original Music Study",target_id=target,style=style,
        candidate_id=sha256((target+style).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )


@pytest.mark.parametrize("mode",GAME_MODES)
def test_six_original_scores_are_deterministic_bounded_and_different(mode):
    one=compose(mode,seed=1294,steps=64)
    assert one==compose(mode,seed=1294,steps=64)
    assert len(one.melody_hz)==len(one.harmony_hz)==64
    assert 50<=one.beats_per_minute<=190
    assert one.note_events>=10
    assert any(note==0 for note in one.melody_hz)
    assert all(0<=n<=2000 for n in one.melody_hz+one.harmony_hz)
    header=emit_score_header(one)
    assert "#define DRAGON_SCORE_STEPS 64" in header
    assert "#define DRAGON_SCORE_INTERVAL" in header
    assert "DRAGON_HARMONY[64]" in header
    assert "DRAGON_MELODY[64]" in header
    assert one.fingerprint!=compose(mode,seed=1295,steps=64).fingerprint


def test_original_scores_per_genre_sound_different():
    evidence={compose(mode,seed=42).fingerprint for mode in GAME_MODES}
    assert len(evidence)==len(GAME_MODES)


def test_unsupported_score_sizes_and_uncertified_modes_rejected():
    with pytest.raises(ValueError):
        compose("fake_console",seed=1)
    with pytest.raises(ValueError):
        compose("racer",seed=1,steps=140)
    with pytest.raises(ValueError):
        compose("racer",seed=-1)
    with pytest.raises(ValueError):
        compose("racer",seed=True)


def test_native_pc_score_is_in_actual_c_engine_not_a_fake_soundtrack_manifest():
    src=_build("pc_linux","roguelike")
    assert "include/dragon_chip_score.h" in src.files
    c=src.files["src/main.c"]
    assert '#include "dragon_chip_score.h"' in c
    assert "DRAGON_SCORE_INTERVAL" in c
    assert "DRAGON_MELODY[beat]" in c
    assert "DRAGON_HARMONY[beat]" in c
    m=json.loads(src.files["dragon-original-music.json"])
    assert m["mode"]=="dungeon" and m["note_events"]>0
    assert m["schema"]=="skeleton.ai.dragon.original_chip_score.v1"


@pytest.mark.parametrize("target,style",[
    ("game_boy","arcade_score_attack"),
    ("game_boy_color","arcade_score_attack"),
    ("game_boy","side_scrolling_platformer"),
])
def test_hardware_game_boy_reward_uses_real_nrxx_audio_registers(target,style):
    cartridge=_build(target,style)
    asm=cartridge.files["src/main.asm"]
    assert "SetupSound:" in asm and "PlayReward:" in asm
    assert "ldh [$FF26],a" in asm
    assert "ldh [$FF24],a" in asm
    assert "ldh [$FF25],a" in asm
    assert "ldh [$FF12],a" in asm
    assert "ldh [$FF14],a" in asm
    assert "    call SetupSound" in asm
    if style=="side_scrolling_platformer":
        assert "    call PlayReward" in asm
    else:
        assert "    call PlayRewardOnce" in asm
    assert "ROM0[$100]" in asm
    assert "src/main.asm" in cartridge.files
