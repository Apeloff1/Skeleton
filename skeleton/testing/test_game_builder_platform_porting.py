"""Platform and homebrew-port capability regression tests.

Coverage is intentionally about deterministic planning, catalog integrity,
source clearance and fail-closed boundaries, not fabricated native binaries.
"""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.platform_registry import (
    PlatformRegistryError, default_registry, list_platforms, lookup_platform, parse_registry,
)
from skeleton.ai.game_builder.port_planner import (
    HomebrewSource, PortMode, PortPlanningError, PortRequest, compile_port, compile_port_route,
)

PROOF_1 = "a" * 64
PROOF_2 = "b" * 64


def original(project: str = "original-puzzle", platform: str = "bandai_wonderswan") -> HomebrewSource:
    return HomebrewSource(
        project_id=project, platform_id=platform, rights_basis="project_owned",
        evidence_sha256=PROOF_1 if project == "original-puzzle" else PROOF_2,
        creative_identity=("original puzzle rules", "dithered ink style", "short session design"),
    )


def test_catalog_is_broad_and_includes_abandoned_and_obscure_systems():
    registry = default_registry()
    summary = registry.summary()
    assert summary["platform_count"] >= 290
    assert len(summary["kinds"]) >= 9
    assert all(count >= 3 for count in summary["kinds"].values())
    for platform_id in (
        "fairchild_channel_f", "interton_vc4000", "epoch_super_cassette_vision",
        "bandai_wonderswan", "bandai_swancrystal", "nec_pc_fx",
        "apple_bandai_pippin", "nuon", "philips_cd_i", "atari_jaguar",
        "commodore_amiga_cd32", "fujitsu_fm_towns_marty", "sinclair_zx81",
        "sharp_x68000", "msx1", "atari_st", "arcade_sega_model3", "arcade_cave_cv1000",
        "ti_84_plus", "symbian_s60", "arduboy", "windows_modern", "sony_ps5",
    ):
        assert registry.get(platform_id).id == platform_id
    assert summary["native_export_verified"] == 0
    assert all(not p.verified_for_native_export for p in registry.profiles.values())


def test_registry_selection_is_sorted_and_does_not_modify_registry():
    registry = default_registry()
    handhelds = list_platforms(kind="handheld", legacy=True)
    assert handhelds and all(p.kind == "handheld" and p.is_legacy for p in handhelds)
    assert tuple(p.id for p in handhelds) == tuple(sorted(p.id for p in handhelds))
    assert lookup_platform("bandai_wonderswan").artifact == "homebrew_rom"
    assert lookup_platform("playdate").render == "one_bit_bitmap"
    assert lookup_platform("pico8_fantasy").artifact == "source_cartridge_or_module"
    assert lookup_platform("nintendo_virtual_boy").render == "monochrome_stereoscopic"
    assert registry.summary() == default_registry().summary()


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version=999),
    lambda d: d["platforms"].append(dict(d["platforms"][0])),
    lambda d: d["platforms"][0].update(toolchain_status="verified"),
    lambda d: d["platforms"][0].update(kind="imaginary"),
    lambda d: d["platforms"][0].update(id="../sneaky"),
    lambda d: d["presets"][d["platforms"][0]["preset"]].update(tier=True),
    lambda d: d["presets"][d["platforms"][0]["preset"]].update(constraints=[]),
    lambda d: d["platforms"][0].update(overrides={"unknown_sdk": "verified"}),
    lambda d: d["platforms"][0].update(overrides={"tier": 5}),
])
def test_registry_rejects_unsafe_or_broken_catalog(mutation):
    data = {"schema_version": 1, "presets": {"p": {
        "tier": 1, "render": "tiles", "sound": "beep", "input": "pad",
        "artifact": "rom", "constraints": ["limited RAM"],
    }}, "platforms": [{
        "id": "old_system", "name": "Old system", "kind": "console",
        "family": "historical", "preset": "p", "lifecycle": "legacy",
        "research_status": "catalogued", "toolchain_status": "unverified",
    }]}
    mutation(data)
    with pytest.raises(PlatformRegistryError):
        parse_registry(json.dumps(data))


def test_direct_port_is_deterministic_and_respects_period_style():
    request = PortRequest((original(),), "nec_pc_fx")
    a = compile_port(request)
    b = compile_port(request)
    assert a == b and len(a.digest) == 64
    assert a.target_platform_id == "nec_pc_fx"
    assert a.mode == "faithful"
    assert "original puzzle rules" in a.design_intent
    assert "target_sdk_and_toolchain_qualification" in a.pending_release_gates
    assert not a.native_build_verified and not a.releasable
    assert not any(action.phase == "visual_upgrade" for action in a.actions)


def test_legacy_to_modern_port_can_enhance_without_losing_heritage():
    p = compile_port(PortRequest((original(),), "windows_modern", PortMode.ENHANCED))
    phases = {a.phase for a in p.actions}
    assert {"mechanics", "visual_upgrade", "simulation_upgrade", "sound_upgrade", "usability_upgrade"} <= phases
    assert "dithered ink style" in p.design_intent
    assert not p.releasable


def test_modern_to_legacy_requires_quantization_and_reverse_work():
    p = compile_port(PortRequest((original(platform="windows_modern"),), "bandai_wonderswan", PortMode.REVERSE_CONSTRAINED))
    phases = {a.phase for a in p.actions}
    assert {"visual_demotion", "gameplay_demotion", "sound_demotion"} <= phases
    assert p.target_platform_id == "bandai_wonderswan"


def test_cross_hybrid_requires_two_distinct_rights_proofs():
    a = original()
    b = original("second-authored-game", "sega_dreamcast")
    p = compile_port(PortRequest((a, b), "linux_desktop", PortMode.CROSS_HYBRID))
    assert p.source_platform_ids == ("bandai_wonderswan", "sega_dreamcast")
    assert "hybrid_design" in {x.phase for x in p.actions}
    assert "hybrid_clearance" in {x.phase for x in p.actions}
    with pytest.raises(PortPlanningError):
        PortRequest((a,), "linux_desktop", PortMode.CROSS_HYBRID)
    with pytest.raises(PortPlanningError):
        PortRequest((a, a), "linux_desktop", PortMode.CROSS_HYBRID)


def test_unknown_or_infringing_sources_are_refused():
    with pytest.raises(PortPlanningError):
        replace(original(), rights_basis="commercial_rom_rip")
    with pytest.raises(PortPlanningError):
        replace(original(), evidence_sha256="")
    with pytest.raises(PortPlanningError):
        compile_port(PortRequest((original(),), "unreleased_imaginary_hardware"))
    with pytest.raises(PlatformRegistryError):
        lookup_platform("../firmware")
    with pytest.raises(PortPlanningError):
        HomebrewSource("some", "bandai_wonderswan", "project_owned", PROOF_1, ())


def test_port_ideas_to_many_destinations_without_conflating_them_with_builds():
    targets = ("windows_modern", "playdate", "arcade_capcom_cps2", "nintendo_famicom")
    plans = compile_port_route(original(), targets)
    assert tuple(p.target_platform_id for p in plans) == targets
    assert len(set(p.digest for p in plans)) == len(targets)
    assert all(not p.releasable for p in plans)
    with pytest.raises(PortPlanningError):
        compile_port_route(original(), ("bandai_wonderswan",))
    with pytest.raises(PortPlanningError):
        compile_port_route(original(), ("windows_modern", "windows_modern"))
    with pytest.raises(PortPlanningError):
        compile_port_route(original(), (), mode=PortMode.FAITHFUL)


def test_changed_proof_or_target_changes_digest():
    one = compile_port(PortRequest((original(),), "windows_modern"))
    two = compile_port(PortRequest((replace(original(), evidence_sha256=PROOF_2),), "windows_modern"))
    three = compile_port(PortRequest((original(),), "macos_modern"))
    assert one.digest != two.digest != three.digest
