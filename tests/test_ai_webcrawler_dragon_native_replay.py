"""Native replay actual C engine recording, reproduction and tamper rejection."""
from __future__ import annotations
from hashlib import sha256
import os
import shutil
import subprocess
import pytest

from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project


def _source():
    return render_native_project(
        title="Dragon Replay",target_id="pc_linux",style="arcade_score_attack",
        candidate_id=sha256(b"original-replay-receipt").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )


def test_bounded_replay_source_binds_to_campaign_and_checksum():
    p=_source()
    assert p.status=="source_generated"
    assert "src/dragon_replay.c" in p.files
    assert "include/dragon_replay.h" in p.files
    assert "src/dragon_replay.c" in p.files["CMakeLists.txt"]
    replay=p.files["src/dragon_replay.c"]
    assert "rd32(header+8)!=signature" in replay
    assert "crc32(payload,size)!=rd32(header+16)" in replay
    assert "DRAGON_REPLAY_MAX_TICKS" in replay
    assert "expected_hash" in replay
    engine=p.files["src/main.c"]
    for flag in ("--record-replay","--play-replay","--replay-selftest"):
        assert flag in engine
    assert "step(unpack_input(loaded.frames[i]))" in engine
    assert "dragon_replay_digest" in engine


def test_replay_is_machine_native_reproducible_and_rejects_corruption(tmp_path):
    if not all(shutil.which(binary) for binary in ("cc","cmake","pkg-config")):
        pytest.skip("native CMake compiler unavailable")
    if subprocess.run(["pkg-config","--exists","sdl2"],capture_output=True,
                      timeout=10).returncode:
        pytest.skip("SDL2 headers unavailable")
    project=_source()
    root=tmp_path/"native"
    for name,body in project.files.items():
        dest=root/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(body,encoding="utf-8")
    config=subprocess.run(["cmake","-S",str(root),"-B",str(root/"build")],
                          timeout=45,capture_output=True,text=True)
    assert config.returncode==0,config.stderr
    compiled=subprocess.run(["cmake","--build",str(root/"build"),"-j","2"],
                            timeout=60,capture_output=True,text=True)
    assert compiled.returncode==0,compiled.stderr
    executable=str(root/"build/dragon_game")
    env={**os.environ,"SDL_VIDEODRIVER":"dummy","SDL_AUDIODRIVER":"dummy",
         "XDG_DATA_HOME":str(tmp_path/"local-state")}
    trace=tmp_path/"gameplay.drpl"
    one=subprocess.run([executable,"--replay-selftest",str(trace)],
        timeout=20,capture_output=True,text=True,env=env)
    assert one.returncode==0,(one.stdout,one.stderr)
    assert "DRAGON_NATIVE_REPLAY_SELFTEST PASS" in one.stdout
    raw=trace.read_bytes()
    assert raw[:4]==b"DRPL" and len(raw)==24+360*2
    two=subprocess.run([executable,"--play-replay",str(trace)],
        timeout=20,capture_output=True,text=True,env=env)
    assert two.returncode==0,(two.stdout,two.stderr)
    assert "DRAGON_NATIVE_REPLAY PASS" in two.stdout
    altered=bytearray(raw)
    altered[-7]^=1
    trace.write_bytes(altered)
    rejected=subprocess.run([executable,"--play-replay",str(trace)],
        timeout=20,capture_output=True,text=True,env=env)
    assert rejected.returncode!=0
    assert "DRAGON_NATIVE_REPLAY PASS" not in rejected.stdout
