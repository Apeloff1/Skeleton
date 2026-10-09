"""Desktop source portability without fraudulent ARM/RISC-V/BSD binary claims."""
from __future__ import annotations
from hashlib import sha256
import json,shutil,subprocess
from pathlib import Path
import pytest
from skeleton.ai.webcrawler.dragon_desktop_abi import (
    DESKTOP_NATIVE,BASE_DESKTOP,ABI_PROFILES,apply_desktop_abi,
)
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_native_projects import EMITTERS,render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_game_design import starter_design,parse_design
from skeleton.ai.webcrawler.dragon_platform_readiness import (
    readiness_for,coverage_report,
)

def _game(target,style="fixed_screen_puzzle"):
    return render_native_project(
        title="Original Dragon Native Portable",
        target_id=target,style=style,
        candidate_id=sha256((target+style).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)

def test_21_actual_desktop_architectures_have_accurate_source_contracts():
    assert len(ABI_PROFILES)==21
    assert len(DESKTOP_NATIVE)==25
    assert len(BASE_DESKTOP)==4
    assert len(EMITTERS)==68
    assert all(p.id==k for k,p in ABI_PROFILES.items())
    assert all(p.arch in ("arm64","x86_64","x86","riscv64")
               for p in ABI_PROFILES.values())
    assert all(p.system in ("Windows","Linux","Darwin","FreeBSD","OpenBSD","NetBSD")
               for p in ABI_PROFILES.values())
    assert len({id for id in DESKTOP_NATIVE})==25
    assert coverage_report()["native_source_count"]==68
    for id in ABI_PROFILES:
        row=readiness_for(id)
        assert row.source_emitter
        assert row.claimed_stage=="native_source_generated"
        assert not row.compiler_verified
        assert "C99/SDL2" in row.native_renderer
        assert row.controller_replay_verified is False

@pytest.mark.parametrize("target,system,arch",[
  ("linux_arm64","Linux","arm64"),
  ("linux_riscv64","Linux","riscv64"),
  ("linux_x86_32","Linux","x86"),
  ("freebsd_amd64","FreeBSD","x86_64"),
  ("freebsd_arm64","FreeBSD","arm64"),
  ("openbsd_amd64","OpenBSD","x86_64"),
  ("netbsd_amd64","NetBSD","x86_64"),
  ("macos_intel","Darwin","x86_64"),
  ("macos_apple_silicon","Darwin","arm64"),
  ("windows_11","Windows","x86_64"),
  ("windows_arm64","Windows","arm64"),
  ("raspberry_pi_5","Linux","arm64"),
  ("asus_rog_ally","Windows","x86_64"),
  ("chromeos_arm","Linux","arm64"),
])
def test_generated_native_pc_game_is_bound_to_correct_machine_abi(target,system,arch):
    p=_game(target)
    assert p.status=="source_generated"
    assert "src/main.c" in p.files
    assert "CMakeLists.txt" in p.files
    assert "cmake/dragon_target_contract.cmake" in p.files
    assert "dragon-desktop-abi.json" in p.files
    data=json.loads(p.files["dragon-desktop-abi.json"])
    assert data["id"]==target
    assert data["system"]==system and data["arch"]==arch
    assert data["compiled"] is False
    assert data["controller_verified"] is False
    assert data["device_verified"] is False
    assert 'include(cmake/dragon_target_contract.cmake)' in p.files["CMakeLists.txt"]
    contract=p.files["cmake/dragon_target_contract.cmake"]
    assert "DRAGON_EXPECTED_SYSTEM" in contract
    assert "CMAKE_SYSTEM_PROCESSOR MATCHES" in contract
    assert f'set(DRAGON_EXPECTED_SYSTEM "{system}")' in contract
    assert f'set(DRAGON_EXPECTED_ARCH "{arch}")' in contract
    assert "native" in p.files["README.abi.md"]
    assert "dragon_game" in p.files["CMakeLists.txt"]

def test_wrong_abi_and_invalid_envelopes_fail_closed():
    with pytest.raises(ValueError):
        apply_desktop_abi("ps5",{"CMakeLists.txt":"project(foo C)"})
    with pytest.raises(ValueError):
        apply_desktop_abi("linux_arm64",{"src/main.c":"main(){}"})
    with pytest.raises(ValueError):
        apply_desktop_abi("linux_arm64",{"CMakeLists.txt":"not a cmake project"})
    row={v["id"]:v for v in target_catalog()}
    for id in ABI_PROFILES:
        assert row[id]["status"]=="native_source"
        assert "arcade_score_attack" in row[id]["supported_styles"]
        assert "fixed_screen_puzzle" in row[id]["supported_styles"]
    for id in ("android_arm64","ios_iphone","tvos","nintendo_switch_2"):
        assert row[id]["supported_styles"]==()

def test_wrong_native_cpu_cannot_be_silently_compiled(tmp_path):
    if not shutil.which("cmake"):
        pytest.skip("CMake unavailable")
    # On normal x86-64 Linux, ARM64 project must fail before SDL2 lookup,
    # otherwise a host ELF could be mislabeled as ARM64-ready.
    import platform
    if platform.system()!="Linux" or platform.machine() not in ("x86_64","amd64"):
        pytest.skip("requires x86-64 Linux host for negative ABI proof")
    project=_game("linux_arm64")
    for path,body in project.files.items():
        destination=tmp_path/path
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(body)
    result=subprocess.run(["cmake","-S",str(tmp_path),"-B",str(tmp_path/"build")],
                           timeout=45,capture_output=True,text=True)
    assert result.returncode!=0
    assert "Dragon native ABI architecture mismatch" in (result.stdout+result.stderr)

def test_editable_source_spec_is_allowed_for_extended_native_linux():
    d=starter_design(title="Original Dragon ARM Quest",target="linux_arm64",
                     genre="roguelike",seed=46)
    d["stages"]=6
    d["candidates"]=3
    g=parse_design(d)
    assert g.target=="linux_arm64"
    assert g.stages==6
    assert g.candidates==3
    with pytest.raises(ValueError):
        bad=dict(d,target="android_arm64")
        parse_design(bad)
