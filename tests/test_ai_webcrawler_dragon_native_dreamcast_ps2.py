"""Dreamcast KOS and PS2SDK original game backends: source, build, limits."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json,os,pytest,shutil,subprocess

from skeleton.ai.webcrawler.dragon_native_dreamcast_ps2 import (
    dreamcast_source,ps2_source,
)
from skeleton.ai.webcrawler.dragon_native_projects import (
    EMITTERS,render_native_project,
)
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

NEW={"dreamcast":"elf","ps2":"elf"}

def source_project(target):
    return render_native_project(
        title="Original Dragon Sixth Generation",
        target_id=target,style="arcade_score_attack",
        candidate_id=sha256(("original"+target).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )

@pytest.mark.parametrize("target,extension",NEW.items())
def test_real_source_generator_not_renamed_rom(target,extension):
    p=source_project(target)
    assert p.target_id==target
    assert p.output==extension
    assert p.status=="source_generated"
    assert "src/main.c" in p.files
    assert "Makefile" in p.files
    assert "README.port.md" in p.files
    assert "dragon-native-manifest.json" in p.files
    assert not any(name.endswith((".elf",".cdi",".iso")) for name in p.files)
    assert p==source_project(target)
    manifest=json.loads(p.files["dragon-native-manifest.json"])
    assert manifest["status"]=="source_generated"
    assert manifest["runtime_gameplay_mode"]=="original_collectible_chase"
    assert manifest["target"]==target
    assert target in EMITTERS
    readiness=readiness_for(target)
    assert readiness.source_emitter
    assert not readiness.compiler_verified
    assert not readiness.controller_replay_verified
    assert readiness.output_extension=="elf"
    item=next(v for v in target_catalog() if v["id"]==target)
    assert item["supported_styles"]==("arcade_score_attack",)
    assert item["status"]=="native_source"
    with pytest.raises(ValueError):
        render_native_project(title="Original Dragon Sixth Generation",
            target_id=target,style="grand_strategy",
            candidate_id="c"*64,mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_dreamcast_real_maple_rgb565_joypad_and_bounded_game():
    c=dreamcast_source(16)["src/main.c"]
    m=dreamcast_source(16)["Makefile"]
    for needle in ("#include <kos.h>","vid_set_mode(DM_320x240_NTSC,PM_RGB565)",
                   "vram_s[py*W+px]","maple_enum_type(0,MAPLE_FUNC_CONTROLLER)",
                   "cont_state_t","maple_dev_status(dev)",
                   "CONT_DPAD_UP","CONT_DPAD_LEFT","CONT_A","CONT_START",
                   "pad->joyx","pad->joyy","thd_sleep(16)",
                   "score++","hp--","shield=45","stage=1+score/4"):
        assert needle in c
    assert "$(KOS_BASE)/Makefile.rules" in m
    assert "KOS_CC" in m and "KOS_LIBS" in m
    assert "dragon_dreamcast.elf" in m
    assert "cdi" not in m

def test_ps2_native_gskit_gs_dma_and_real_pad_rpc():
    c=ps2_source(17)["src/main.c"]
    m=ps2_source(17)["Makefile"]
    for needle in ("#include <sifrpc.h>","#include <libpad.h>",
                   "#include <gsKit.h>","#include <dmaKit.h>",
                   "pad_storage[256] __attribute__((aligned(64)))",
                   "SifInitRpc(0)","padInit(0)","padPortOpen(0,0,pad_storage)",
                   "padGetState(0,0)","padRead(0,0,&st)",
                   "PAD_STATE_STABLE","PAD_CROSS","PAD_START",
                   "gsKit_init_global","dmaKit_init(","gsKit_init_screen",
                   "GS_SETREG_RGBAQ","gsKit_prim_sprite",
                   "gsKit_queue_exec","gsKit_sync_flip",
                   "gsKit_queue_reset","score++","hp--"):
        assert needle in c
    assert "EE_BIN := dragon_ps2.elf" in m
    assert "EE_LIBS := -lpad -lgskit -ldmakit -lm" in m
    assert "$(PS2SDK)/samples/Makefile.eeglobal" in m

@pytest.mark.parametrize("func",[dreamcast_source,ps2_source])
def test_seed_bounds_and_independent_output(func):
    assert func(7)==func(7)
    assert func(7)!=func(9)
    for bad in (True,-1,2**32,2.0,None,"7"):
        with pytest.raises(ValueError):
            func(bad)

@pytest.mark.parametrize("target,environment,compiler",[
    ("dreamcast","KOS_BASE","sh-elf-gcc"),
    ("ps2","PS2SDK","mips64r5900el-ps2-elf-gcc"),
])
def test_native_sdk_compilation_only_when_exact_compiler_installed(
    tmp_path,target,environment,compiler,
):
    if not shutil.which("make") or not shutil.which(compiler) or (
        not os.environ.get(environment)
    ) or (target=="ps2" and not os.environ.get("GSKIT")):
        pytest.skip("exact open SDK/target compiler not installed")
    source=dreamcast_source(44) if target=="dreamcast" else ps2_source(44)
    for path,body in source.items():
        output=tmp_path/path
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(body)
    result=subprocess.run(["make","-C",str(tmp_path),"all"],
        capture_output=True,text=True,timeout=120)
    assert result.returncode==0,(result.stdout,result.stderr)
    binary=tmp_path/("dragon_dreamcast.elf" if target=="dreamcast" else "dragon_ps2.elf")
    assert binary.is_file() and binary.stat().st_size>0
    assert binary.read_bytes().startswith(b"\x7fELF")
