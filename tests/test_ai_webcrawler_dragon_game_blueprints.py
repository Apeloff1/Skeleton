"""Deterministic original world generation and actual native SDL runtime gates."""
from __future__ import annotations
from collections import deque
from pathlib import Path
import json
import os
import shutil
import subprocess
import pytest
from skeleton.ai.webcrawler.dragon_game_blueprints import (
    GAME_MODES, GENRES, PALETTES, W, H, design_campaign, PRNG,
)
from skeleton.ai.webcrawler.dragon_native_arcade_runtime import render_sdl_campaign
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

MODES={
    "arcade_score_attack":"arena",
    "side_scrolling_platformer":"platform",
    "top_down_adventure":"adventure",
    "roguelike":"dungeon",
    "tactical_rpg":"tactics",
    "racing":"racer",
}

def walkable(stage):
    q=deque([stage.start]);seen={stage.start}
    while q:
        x,y=q.popleft()
        if (x,y)==stage.goal:return True
        for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0<=nx<W and 0<=ny<H and (nx,ny) not in seen:
                if stage.terrain[ny][nx] not in '#^~':
                    seen.add((nx,ny));q.append((nx,ny))
    return False

@pytest.mark.parametrize("style,mode",MODES.items())
@pytest.mark.parametrize("seed",[0,1,123,0xDEADBEEF])
def test_game_engines_build_connected_unique_real_campaigns(style,mode,seed):
    c=design_campaign(style=style,seed=seed,stages=4)
    assert c==design_campaign(style=style,seed=seed,stages=4)
    assert c.verified_generation and c.mode==mode
    assert len(c.stages)==4 and len({s.checksum for s in c.stages})==4
    assert c.mechanics and c.objectives
    for stage in c.stages:
        assert stage.width==W and stage.height==H
        assert len(stage.terrain)==H and all(len(row)==W for row in stage.terrain)
        assert stage.terrain[stage.start[1]][stage.start[0]]=="S"
        assert stage.terrain[stage.goal[1]][stage.goal[0]]=="G"
        assert stage.pickups>0 and stage.enemies>0
        assert walkable(stage),f"{style} stage {stage.stage_id} has unreachable exit"

def test_different_eras_seeds_and_palettes_are_not_identical():
    one=design_campaign(style="racing",seed=15,palette="cga")
    two=design_campaign(style="racing",seed=16,palette="modern_neon")
    assert one.id!=two.id
    assert one.stages[0].terrain!=two.stages[0].terrain
    assert len(PALETTES)>=5
    assert "GAME_MODE" in render_sdl_campaign(one)["include/dragon_campaign.h"]

def test_uint32_prng_and_untrusted_campaign_constraints():
    assert [PRNG(1).u32() for _ in range(2)]==[270369,270369]
    with pytest.raises(ValueError):
        PRNG(-1)
    with pytest.raises(ValueError):
        PRNG(True)
    with pytest.raises(ValueError):
        design_campaign(style="unknown",seed=2)
    with pytest.raises(ValueError):
        design_campaign(style="racing",seed=2,stages=20)
    with pytest.raises(ValueError):
        design_campaign(style="racing",seed=2,palette="../../")
    with pytest.raises(ValueError):
        design_campaign(style="racing",seed=2,stages=True)

@pytest.mark.parametrize("style,mode",MODES.items())
def test_full_sdl_source_is_native_and_contains_distinct_gameplay_rules(style,mode):
    from hashlib import sha256
    src=render_native_project(
        title="Dragon World",target_id="pc_linux",style=style,
        candidate_id=sha256(("native-"+style).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.PHYSICS,Mechanic.PLATFORMING),
        authorized=True,
    )
    assert src.status=="source_generated"
    assert "dragon-campaign.json" in src.files
    campaign=json.loads(src.files["dragon-campaign.json"])
    assert campaign["mode"]==mode and len(campaign["stages"])==4
    code=src.files["src/main.c"]
    assert "SDL_GameControllerGetButton" in code
    assert "SDL_OpenAudioDevice" in code
    assert "begin_stage(" in code
    assert "projectile_update" in code
    assert "GAME_MODE==4" in code
    assert "GAME_MODE==1" in code
    assert "GAME_MODE==5" in code
    assert "void" in code and "<html" not in code
    assert "--smoke" in code
    assert src.files["include/dragon_campaign.h"].count("STAGE_COUNT 4")==1

def test_unsupported_abstract_genres_cannot_fake_playable_implementations():
    from hashlib import sha256
    with pytest.raises(ValueError,match="gameplay genre"):
        render_native_project(
            title="Dragon Realm",target_id="pc_linux",style="grand_strategy",
            candidate_id=sha256(b"unknown").hexdigest(),
            mechanics=(Mechanic.MOVEMENT,),authorized=True,
        )
    with pytest.raises(ValueError,match="target has not implemented"):
        render_native_project(
            title="Dragon Realm",target_id="game_boy",style="racing",
            candidate_id=sha256(b"unknown").hexdigest(),
            mechanics=(Mechanic.MOVEMENT,),authorized=True,
        )

@pytest.mark.parametrize("style",MODES)
def test_build_and_run_native_sdl_campaign_on_real_toolchain(tmp_path,style):
    if not shutil.which("cmake") or not shutil.which("cc"):
        pytest.skip("CMake or native C compiler unavailable")
    probe=subprocess.run(["pkg-config","--exists","sdl2"],
        check=False,timeout=10,capture_output=True)
    if probe.returncode:
        pytest.skip("SDL2 development headers unavailable")
    from hashlib import sha256
    project=render_native_project(
        title="Original Campaign",target_id="pc_linux",style=style,
        candidate_id=sha256(style.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    root=tmp_path/style
    for name,body in project.files.items():
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(body,encoding="utf-8")
    cfg=subprocess.run(["cmake","-S",str(root),"-B",str(root/"build")],
                       timeout=40,capture_output=True,text=True)
    assert cfg.returncode==0,cfg.stderr
    build=subprocess.run(["cmake","--build",str(root/"build"),"-j","2"],
                         timeout=60,capture_output=True,text=True)
    assert build.returncode==0,build.stderr
    exe=root/"build/dragon_game"
    assert exe.is_file()
    env={**os.environ,"SDL_VIDEODRIVER":"dummy","SDL_AUDIODRIVER":"dummy"}
    test=subprocess.run([str(exe),"--smoke"],env=env,
                        timeout=20,capture_output=True,text=True)
    assert test.returncode==0,(test.stdout,test.stderr)
    assert "DRAGON_NATIVE_SMOKE_OK" in test.stdout
