"""Original Thumby device game: actual button/audio/OLED APIs and replay tests."""
from __future__ import annotations
from hashlib import sha256
from types import SimpleNamespace
import json,py_compile,subprocess,sys,shutil
from pathlib import Path
import pytest
from skeleton.ai.webcrawler.dragon_native_thumby import thumby_source
from skeleton.ai.webcrawler.dragon_native_projects import (
    EMITTERS,render_native_project,
)
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for,coverage_report


def generated():
    return render_native_project(
        title="Original Dragon Micro Quest",target_id="thumby",
        style="arcade_score_attack",
        candidate_id=sha256(b"thumby original 72x40 game").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )


def game():
    source=generated().files["Games/DragonMicroQuest/DragonMicroQuest.py"]
    namespace={"__name__":"dragon_test"}
    compile(source,"<thumby-original-game>","exec")
    exec(source,namespace)
    return namespace


def test_exact_thumby_source_is_real_device_application_and_hardware_ready_only_as_source():
    p=generated()
    assert p.status=="source_generated"
    assert p.target_id=="thumby" and p.output=="py"
    assert p.files==generated().files
    assert "Games/DragonMicroQuest/DragonMicroQuest.py" in p.files
    assert "Makefile" in p.files
    source=p.files["Games/DragonMicroQuest/DragonMicroQuest.py"]
    for binding in ("device.display.setFPS(30)","d.blit(DRAGON",
        "d.blit(CRYSTAL","d.blit(FOE","d.update()",
        "thumby.buttonU.pressed()","thumby.buttonD.pressed()",
        "thumby.buttonL.pressed()","thumby.buttonR.pressed()",
        "thumby.buttonA.justPressed()","thumby.buttonB.justPressed()",
        "device.audio.play(","if __name__==\"__main__\""):
        assert binding in source
    assert "SDL_" not in source and "WinMain" not in source
    assert "import wifi" not in source
    assert "import requests" not in source
    info=json.loads(p.files["dragon-micro-hardware.json"])
    assert info["screen"]=={"width":72,"height":40,"bits_per_pixel":1}
    assert info["device_tested"] is False
    assert info["usb_flash_performed"] is False
    assert "upload" not in p.files["Makefile"]
    manifest=json.loads(p.files["dragon-native-manifest.json"])
    assert manifest["output_extension"]=="py"
    assert manifest["status"]=="source_generated"
    assert "thumby" in EMITTERS
    assert coverage_report()["native_source_count"]==77
    assert coverage_report()["missing_native_source_count"]==92
    assert not readiness_for("thumby").compiler_verified


def test_original_thumby_gameplay_is_deterministic_and_bounded_on_actual_screen():
    n=game()
    a,b=n["fresh"](1234),n["fresh"](1234)
    assert a==b
    assert a[n["MODE"]]==n["READY"]
    n["step"](a,0,n["ACTION_A"])
    n["step"](b,0,n["ACTION_A"])
    assert a[n["MODE"]]==n["PLAYING"]
    assert b==a
    for frame in range(800):
        hold=[n["UP"],n["DOWN"],n["LEFT"],n["RIGHT"],0][frame%5]
        action=n["ACTION_A"] if frame%43==0 else (
            n["ACTION_B"] if frame%79==0 else 0)
        e=n["step"](a,hold,action)
        assert n["step"](b,hold,action)==e
        assert a==b
        assert 1<=a[n["HX"]]<=63 and 10<=a[n["HY"]]<=31
        assert 3<=a[n["GX"]]<=62 and 11<=a[n["GY"]]<=29
        assert 0<=a[n["HP"]]<=3
        assert a[n["MODE"]] in (n["PLAYING"],n["DEFEAT"],n["VICTORY"])
        if a[n["MODE"]]!=n["PLAYING"]:
            assert n["step"](a,0,n["ACTION_A"])==5
            assert n["step"](b,0,n["ACTION_A"])==5


def test_crystal_score_stage_victory_damage_and_retries_are_actual_state_rules():
    n=game()
    s=n["fresh"](7)
    assert n["step"](s,0,n["ACTION_A"])==5
    s[n["GX"]]=s[n["HX"]]
    s[n["GY"]]=s[n["HY"]]
    assert n["step"](s,0,0)==1
    assert s[n["SCORE"]]==1
    assert s[n["STAGE"]]==1
    s[n["SCORE"]]=15
    s[n["GX"]]=s[n["HX"]]
    s[n["GY"]]=s[n["HY"]]
    assert n["step"](s,0,0)==4
    assert s[n["MODE"]]==n["VICTORY"]
    assert s[n["SCORE"]]==16 and s[n["STAGE"]]==5
    assert n["step"](s,0,n["ACTION_A"])==5
    assert s[n["MODE"]]==n["PLAYING"]
    assert s[n["SCORE"]]==0 and s[n["HP"]]==3

    # Collision is not decorative: it takes HP and provides temporary
    # invulnerability, preventing damage on every succeeding frame.
    s[n["GX"]]=3
    s[n["GY"]]=10
    s[n["EX"]]=s[n["HX"]]
    s[n["EY"]]=s[n["HY"]]
    assert n["step"](s,0,0)==2
    assert s[n["HP"]]==2 and s[n["GUARD"]]==32
    assert n["step"](s,0,0)!=2
    s[n["GUARD"]]=0
    s[n["EX"]]=s[n["HX"]]
    s[n["EY"]]=s[n["HY"]]
    assert n["step"](s,0,0)==2
    assert s[n["HP"]]==1
    s[n["GUARD"]]=0
    s[n["EX"]]=s[n["HX"]]
    s[n["EY"]]=s[n["HY"]]
    assert n["step"](s,0,0)==2
    assert s[n["HP"]]==0 and s[n["MODE"]]==n["DEFEAT"]


class FakeButton:
    def pressed(self):return False
    def justPressed(self):return False

class FakeDisplay:
    width=72
    height=40
    def __init__(self):self.fps=None;self.frames=0;self.ops=0
    def setFPS(self,n):self.fps=n
    def fill(self,*args):self.ops+=1
    def drawText(self,*args):self.ops+=1
    def drawFilledRectangle(self,*args):self.ops+=1
    def drawRectangle(self,*args):self.ops+=1
    def blit(self,*args):
        self.ops+=1
        bitmap,x,y,w,h,*rest=args
        assert len(bitmap)==w*((h+7)//8)
        assert -8<x<73 and -8<y<41
    def update(self):self.frames+=1

class FakeAudio:
    def __init__(self):self.events=[]
    def play(self,hz,ms):self.events.append((hz,ms))


def test_entire_72x40_native_device_loop_runs_against_exact_api_without_flashing():
    n=game()
    display=FakeDisplay()
    audio=FakeAudio()
    b=FakeButton()
    device=SimpleNamespace(display=display,audio=audio,
        buttonU=b,buttonD=b,buttonL=b,buttonR=b,buttonA=b,buttonB=b)
    frames=[0]
    def buttons():
        tick=frames[0];frames[0]+=1
        return (n["RIGHT"] if tick%2 else n["DOWN"],
                n["ACTION_A"] if tick==0 or tick==35 else 0)
    end=n["run"](max_frames=128,read_buttons=buttons,device=device)
    assert display.fps==30 and display.frames==128
    assert display.ops>250
    assert end[n["TICK"]]>50
    assert end[n["MODE"]] in (n["PLAYING"],n["DEFEAT"],n["VICTORY"])
    assert all(a in (659,196,440,988) for a,_ in audio.events)


def test_thumby_source_is_installable_without_automatic_device_access(tmp_path):
    project=generated()
    for name,content in project.files.items():
        target=tmp_path/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content,encoding="utf-8")
    source=tmp_path/"Games/DragonMicroQuest/DragonMicroQuest.py"
    py_compile.compile(str(source),doraise=True)
    assert source.stat().st_size>4500
    if shutil.which("make"):
        result=subprocess.run(["make","-C",str(tmp_path),"check"],
               capture_output=True,text=True,timeout=15)
        assert result.returncode==0,(result.stdout,result.stderr)
    assert not any(p.suffix in (".uf2",".bin",".hex") for p in tmp_path.rglob("*"))


@pytest.mark.parametrize("bad",(-1,2**32,True,1.0,"injected",None))
def test_tiny_device_emitter_rejects_non_uint32_seeds(bad):
    with pytest.raises(ValueError):
        thumby_source(bad)
