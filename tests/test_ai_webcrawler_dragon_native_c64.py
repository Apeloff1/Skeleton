"""Real MOS6510 C64 source and optional cc65 PRG compile validation."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import pytest
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic


def game():
    return render_native_project(title="Dragon Treasure",target_id="commodore_64",
        style="arcade_score_attack",candidate_id=sha256(b"c64-original").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True)


def test_c64_uses_cia_and_vic_and_sid_not_sdl2_or_html():
    p=game()
    assert p.status=="source_generated" and p.output=="prg"
    source=p.files["src/main.c"]
    assert "0x0400" in source and "0xD800" in source
    assert "0xDC00" in source and "0xD400" in source
    assert "pad&1" in source and "SID[4]" in source
    assert "CL65" in p.files["Makefile"]
    assert ".prg" in p.files["Makefile"]
    assert "<html" not in source and "SDL_" not in source


def test_real_c64_prg_if_cc65_available(tmp_path):
    cl65=shutil.which("cl65")
    if not cl65:
        pytest.skip("cc65 native 6510 compiler is not installed")
    p=game()
    for name,body in p.files.items():
        out=tmp_path/name
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(body,encoding="utf-8")
    result=subprocess.run([cl65,"-t","c64","-O","-o",
        str(tmp_path/"dragon.prg"),str(tmp_path/"src/main.c")],
        timeout=60,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    compiled=(tmp_path/"dragon.prg").read_bytes()
    assert len(compiled)>100
    # Standard C64 PRG load address $0801, not a "pretend" extension.
    assert compiled[:2]==b"\x01\x08"
