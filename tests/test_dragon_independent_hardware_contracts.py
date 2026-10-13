"""Independent Dragon platform metadata and source-generation contracts.

This integration test deliberately does not claim compiler, emulator or
physical device acceptance. The full Dragon target registry is integrated
separately in #3763.
"""
from __future__ import annotations

import json

import pytest

from skeleton.ai.webcrawler.dragon_compatible_revisions import (
    COMPATIBILITY, REVISIONS,
)
from skeleton.ai.webcrawler.dragon_desktop_abi import (
    ABI_PROFILES, apply_desktop_abi,
)
from skeleton.ai.webcrawler.dragon_native_thumby import thumby_source
from skeleton.ai.webcrawler.dragon_platform_expansion import (
    SUPPLEMENTAL_TARGETS, supplemental_targets,
)


def test_supplemental_hardware_is_distinct_and_evidence_labeled():
    rows = supplemental_targets()
    assert rows == SUPPLEMENTAL_TARGETS
    assert len(rows) == 122
    assert len({r.id for r in rows}) == len(rows)
    assert all(1972 <= r.year <= 2026 for r in rows)
    assert all(r.cpu and r.graphics and r.toolchain for r in rows)
    assert all(r.status in {
        "toolchain_adapter", "licensed_sdk", "historical_reference", "native_source",
    } for r in rows)
    assert any(r.status == "licensed_sdk" for r in rows)
    assert any(r.status == "historical_reference" for r in rows)


def test_compatible_revisions_have_nonduplicated_parent_and_destination():
    assert len(REVISIONS) == len(COMPATIBILITY) == 15
    assert all(r.target != r.parent and r.parent not in COMPATIBILITY for r in REVISIONS)
    assert all(r.assumption and r.required_test for r in REVISIONS)


def test_desktop_abi_rejects_unrecognized_targets_and_wrong_inputs():
    assert len(ABI_PROFILES) == 21
    with pytest.raises(ValueError):
        apply_desktop_abi("ps5", {"CMakeLists.txt": "project(a C)\\n"})
    with pytest.raises(ValueError):
        apply_desktop_abi("linux_arm64", {"src/main.c": "int main(void){return 0;}"})
    with pytest.raises(ValueError):
        apply_desktop_abi("linux_arm64", {"CMakeLists.txt": "not cmake"})


def test_desktop_abi_requires_correct_system_and_cpu_at_build_time():
    original = "cmake_minimum_required(VERSION 3.22)\\nproject(dragon_game C)\\n"
    patched = apply_desktop_abi("linux_arm64", {"CMakeLists.txt": original})
    assert 'include(cmake/dragon_target_contract.cmake)' in patched["CMakeLists.txt"]
    contract = patched["cmake/dragon_target_contract.cmake"]
    assert 'set(DRAGON_EXPECTED_SYSTEM "Linux")' in contract
    assert 'set(DRAGON_EXPECTED_ARCH "arm64")' in contract
    assert "FATAL_ERROR" in contract
    receipt = json.loads(patched["dragon-desktop-abi.json"])
    assert receipt["compiled"] is False
    assert receipt["device_verified"] is False
    assert receipt["signed_package"] is False
    assert original == "cmake_minimum_required(VERSION 3.22)\\nproject(dragon_game C)\\n"


def test_original_thumby_source_is_deterministic_and_never_auto_deploys():
    generated = thumby_source(1234)
    assert generated == thumby_source(1234)
    script = generated["Games/DragonMicroQuest/DragonMicroQuest.py"]
    compile(script, "<original-thumby-game>", "exec")
    assert "if __name__==\"__main__\":" in script
    receipt = json.loads(generated["dragon-micro-hardware.json"])
    assert receipt["device_tested"] is False
    assert receipt["usb_flash_performed"] is False
    assert "mpremote" not in generated["Makefile"].split("deploy:", 1)[1]
    assert "no unattended flashing" in generated["Makefile"]


@pytest.mark.parametrize("seed", [-1, 2**32, "4", 1.5, True])
def test_thumby_rejects_invalid_seed(seed):
    with pytest.raises(ValueError):
        thumby_source(seed)


def test_thumby_simulation_is_replayable_without_hardware():
    script = thumby_source(999)["Games/DragonMicroQuest/DragonMicroQuest.py"]
    env = {"__name__": "dragon_test"}
    exec(compile(script, "<thumby-simulation>", "exec"), env)
    first = env["fresh"](999)
    second = env["fresh"](999)
    assert first == second
    env["step"](first, 0, env["ACTION_A"])
    env["step"](second, 0, env["ACTION_A"])
    assert first == second
    for frame in range(250):
        held = (env["UP"], env["DOWN"], env["LEFT"], env["RIGHT"], 0)[frame % 5]
        pressed = env["ACTION_B"] if frame % 41 == 0 else 0
        assert env["step"](first, held, pressed) == env["step"](second, held, pressed)
        assert first == second
        assert 1 <= first[env["HX"]] <= 63
        assert 10 <= first[env["HY"]] <= 31
