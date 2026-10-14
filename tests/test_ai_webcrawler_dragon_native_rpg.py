"""Real discrete native RPG combat, mana, character leveling and chapter state."""
from __future__ import annotations
from hashlib import sha256
import os,shutil,subprocess,json
import pytest
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic


def game():
    return render_native_project(
        title="Dragon Original RPG",target_id="pc_linux",
        style="turn_based_rpg",candidate_id=sha256(b"original-rpg").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)


def test_real_turn_based_native_mechanics_not_same_roguelike_skin():
    p=game()
    src=p.files["src/main.c"]
    assert "enum {EXPLORE=0,BATTLE=1,DEFEAT=2,VICTORY=3}" in src
    assert "resolve_battle(int action)" in src
    assert "static void levelup(void)" in src
    assert "enemy_turn(Enemy*e)" in src
    assert "game.hero.mp-=3" in src
    assert "game.hero.potions--" in src
    assert "game.hero.guard=1" in src
    assert "game.hero.xp+=xp" in src
    assert "game.hero.maxhp+=3" in src
    assert "game.guardians==0" in src
    assert "game.hero.keys--" in src
    assert 'strcmp(argv[1],"--smoke")' in src
    assert "SDL_CONTROLLER_BUTTON_X" in src
    manifest=json.loads(p.files["dragon-native-manifest.json"])
    assert manifest["runtime_gameplay_mode"]=="native_turn_based_rpg"
    assert manifest["campaign_stages"]==4
    assert p.status=="source_generated"
    assert "CMakeLists.txt" in p.files
    assert "src/dragon_save.c" not in p.files  # distinct RPG runtime; saves not claimed
    assert "src/dragon_replay.c" not in p.files
    other=render_native_project(
        title="Dragon Original RPG",target_id="pc_linux",
        style="roguelike",candidate_id=sha256(b"original-rpg").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)
    assert p.files["src/main.c"] != other.files["src/main.c"]


def test_native_rpg_compilation_and_actual_turn_fight_smoke(tmp_path):
    if not all(shutil.which(x) for x in ("cc","cmake","pkg-config")):
        pytest.skip("native compiler/CMake not installed")
    if subprocess.run(["pkg-config","--exists","sdl2"],
       timeout=10,capture_output=True).returncode:
        pytest.skip("SDL2 development headers absent")
    src=game()
    root=tmp_path/"rpg"
    for name,body in src.files.items():
        dest=root/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(body,encoding="utf-8")
    c=subprocess.run(["cmake","-S",str(root),"-B",str(root/"build")],
        timeout=40,capture_output=True,text=True)
    assert c.returncode==0,c.stderr
    b=subprocess.run(["cmake","--build",str(root/"build"),"-j","2"],
        timeout=60,capture_output=True,text=True)
    assert b.returncode==0,b.stderr
    runtime=subprocess.run([str(root/"build/dragon_game"),"--smoke"],
        timeout=20,capture_output=True,text=True,
        env={**os.environ,"SDL_VIDEODRIVER":"dummy","SDL_AUDIODRIVER":"dummy"})
    assert runtime.returncode==0,(runtime.stdout,runtime.stderr)
    assert "DRAGON_TURN_RPG_SMOKE PASS" in runtime.stdout
