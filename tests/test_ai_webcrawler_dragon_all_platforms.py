"""Every Dragon platform must have an honest inventory and a bounded gate."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import shutil,subprocess
import pytest

from skeleton.ai.webcrawler.dragon_platform_expansion import SUPPLEMENTAL_TARGETS
from skeleton.ai.webcrawler.dragon_native_targets import (
    BASE_TARGETS,TARGETS,CATALOG,target_catalog,demand_target,STYLES,practice_matrix,
)
from skeleton.ai.webcrawler.dragon_platform_readiness import (
    SOURCE_RENDERERS,readiness_for,coverage_report,readiness_json,
)
from skeleton.ai.webcrawler.dragon_native_projects import EMITTERS,render_native_project
from skeleton.ai.webcrawler.dragon_native_legacy_expansion import native_legacy_source
from skeleton.ai.webcrawler.dragon_hardware_budget import budget_for
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

LEGACY_NEW=("atari_2600","apple_ii","zx_spectrum","dos_8086","windows_95")

def test_comprehensive_hardware_inventory_has_no_duplicates_or_lost_eras():
    assert len(BASE_TARGETS)==47
    assert len(SUPPLEMENTAL_TARGETS)==122
    assert len(TARGETS)==len(CATALOG)==169
    assert len({t.id for t in TARGETS})==169
    assert len({t.id for t in SUPPLEMENTAL_TARGETS})==122
    assert len(EMITTERS)==48
    assert all(t.year>=1972 and t.year<=2026 for t in TARGETS)
    for ident in ("vectrex","atari_5200","atari_7800","zx_spectrum_next",
        "commodore_vic20","bbc_micro","msx1","amstrad_cpc",
        "sega_cd","sega_32x","atari_jaguar","wonderswan",
        "dreamcast","nintendo_switch","nintendo_switch_2",
        "ps5","ps5_pro","xbox_series_s","xbox_series_x",
        "steam_deck","windows_95","windows_11","linux_arm64",
        "linux_riscv64","macos_apple_silicon","freebsd_amd64",
        "raspberry_pi_5","android_arm64","ios_iphone","playdate"):
        assert ident in CATALOG

@pytest.mark.parametrize("target",sorted(CATALOG))
def test_every_identified_system_has_actionable_truthful_readiness(target):
    record=readiness_for(target)
    assert record.target==target
    assert record.year==CATALOG[target].year
    assert record.cpu and record.graphics_hardware
    assert record.source_emitter==(target in EMITTERS)
    assert record.claimed_stage==(
        "native_source_generated" if target in EMITTERS else "catalog_only")
    assert record.compiler_verified is False
    assert record.controller_replay_verified is False
    assert record.physical_hardware_verified is False
    assert record.distribution_approved is False
    assert record.toolchain
    assert record.next_gate
    assert record.supported_styles or not record.source_emitter
    if target not in EMITTERS:
        assert record.native_renderer=="NOT IMPLEMENTED"
        assert record.supported_styles==()
    else:
        assert record.native_renderer!="NOT IMPLEMENTED"
        assert record.next_gate.startswith("Install exact target SDK")

def test_curated_platform_report_never_claims_all_consumer_devices_implemented():
    report=coverage_report()
    assert report["catalog_count"]==169
    assert report["native_source_count"]==48
    assert report["missing_native_source_count"]==121
    assert report["source_coverage_fraction"]==round(48/169,6)
    assert report["compiler_verified_count"]==0
    assert report["emulator_verified_count"]==0
    assert report["physical_hardware_verified_count"]==0
    assert len(report["hardware_ids"])==169
    assert len(report["source_ids"])==48
    assert len(report["next_unimplemented"])==121
    assert "not literally every SKU" in report["coverage_scope"]
    digest=report.pop("digest")
    assert sha256(json.dumps(report,sort_keys=True,separators=(",",":"),
              ensure_ascii=True).encode()).hexdigest()==digest
    export=json.loads(readiness_json())
    assert len(export["targets"])==169
    assert export["coverage"]["digest"]==digest
    assert all(t["schema"]=="skeleton.ai.dragon.target_readiness.v1"
               for t in export["targets"])

def test_incapable_and_licensed_hardware_remain_fail_closed():
    entry=readiness_for("magnavox_odyssey")
    assert entry.status=="historical_reference"
    assert not entry.source_emitter
    assert "non-programmable" in entry.next_gate
    assert readiness_for("nintendo_switch_2").status=="licensed_sdk"
    assert readiness_for("ps5_pro").status=="licensed_sdk"
    for target in ("magnavox_odyssey","nintendo_switch_2",
                   "android_arm64","windows_11","ps5"):
        with pytest.raises((ValueError,PermissionError)):
            render_native_project(
                title="Dragon must not fake code",target_id=target,
                style="arcade_score_attack",candidate_id="e"*64,
                mechanics=(Mechanic.MOVEMENT,),authorized=True)

@pytest.mark.parametrize("target",LEGACY_NEW)
def test_new_native_system_has_original_gameplay_and_correct_build_target(target):
    project=render_native_project(
        title="Original Dragon Legacy Quest",target_id=target,
        style="arcade_score_attack",candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )
    assert project.target_id==target
    assert project.status=="source_generated"
    assert project==render_native_project(
        title="Original Dragon Legacy Quest",target_id=target,
        style="arcade_score_attack",candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)
    assert len(project.files)>=5
    assert "Makefile" in project.files and "README.port.md" in project.files
    assert "CMakeLists.txt" not in project.files
    manifest=json.loads(project.files["dragon-native-manifest.json"])
    assert manifest["target"]==target
    assert manifest["status"]=="source_generated"
    assert "source" in project.files["README.md"].lower()
    assert budget_for(target).console_family
    assert all(not name.endswith((".exe",".tap",".rom",".bin")) for name in project.files)
    assert "arcade_score_attack" in next(x for x in target_catalog()
                                      if x["id"]==target)["supported_styles"]
    with pytest.raises(ValueError):
        render_native_project(
            title="Original Dragon Legacy Quest",target_id=target,
            style="grand_strategy",candidate_id="f"*64,
            mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_distinct_native_api_contracts_not_a_renamed_desktop_game():
    code={id:native_legacy_source(id,83) for id in LEGACY_NEW}
    apple=code["apple_ii"]["src/main.c"]
    zx=code["zx_spectrum"]["src/main.c"]
    dos=code["dos_8086"]["src/main.c"]
    win=code["windows_95"]["src/main.c"]
    atari=code["atari_2600"]["src/main.asm"]
    assert "cgetc()" in apple and "-t apple2" in code["apple_ii"]["Makefile"]
    assert "getch()" in zx and "+zx" in code["zx_spectrum"]["Makefile"]
    assert "clrscr()" in dos and "-bt=dos" in code["dos_8086"]["Makefile"]
    assert "WinMain" in win and "WM_PAINT" in win and "WM_TIMER" in win
    assert "CreateWindowA" in win and "-mwindows" in code["windows_95"]["Makefile"]
    assert "WSYNC" in atari and "SWCHA" in atari and "DragonSprite:" in atari
    assert "org $FFFC" in atari and "-f3" in code["atari_2600"]["Makefile"]
    assert len(set(sha256(("".join(v.values())).encode()).hexdigest()
                   for v in code.values()))==5
    for target in LEGACY_NEW:
        for bad in (True,-1,2**32,"wrong",1.0):
            with pytest.raises(ValueError):
                native_legacy_source(target,bad)

def test_apple_ii_native_cc65_compile_when_toolchain_is_present(tmp_path):
    if not shutil.which("cl65") or not shutil.which("make"):
        pytest.skip("cc65 / make unavailable")
    files=native_legacy_source("apple_ii",123)
    for name,data in files.items():
        dest=tmp_path/name;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(data)
    result=subprocess.run(["make","-C",str(tmp_path)],timeout=65,
                          capture_output=True,text=True)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert (tmp_path/"build/dragon.bin").stat().st_size>0

@pytest.mark.parametrize("target,tool",[
    ("zx_spectrum","zcc"),("atari_2600","dasm"),
    ("dos_8086","wcl"),("windows_95","i686-w64-mingw32-gcc"),
])
def test_native_cross_compiler_build_when_installed(tmp_path,target,tool):
    if not shutil.which(tool) or not shutil.which("make"):
        pytest.skip("target cross compiler not installed: "+tool)
    files=native_legacy_source(target,22)
    for name,data in files.items():
        dest=tmp_path/name;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(data)
    result=subprocess.run(["make","-C",str(tmp_path)],timeout=90,
                          capture_output=True,text=True)
    assert result.returncode==0,(result.stdout,result.stderr)
    expected={"zx_spectrum":"dragon.tap","atari_2600":"dragon.bin",
              "dos_8086":"dragon.exe","windows_95":"dragon.exe"}[target]
    assert (tmp_path/"build"/expected).stat().st_size>0
