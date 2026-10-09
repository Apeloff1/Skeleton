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
from skeleton.ai.game_builder.desktop_native_export import (
    NativeDesktopExportError, compile_native_desktop, export_native_desktop_source,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.editor_platforms import (
    editor_platform_form, editor_platform_options, editor_portability_context,
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


def test_editor_exposes_all_platforms_without_fake_native_exporters():
    registry = default_registry()
    form = editor_platform_form()
    assert len(form["source_options"]) == len(registry.profiles)
    assert len(form["target_options"]) == len(registry.profiles)
    assert len(form["port_modes"]) == 4
    assert form["export_status"] == "no_native_target_verified"
    assert all(not option["verified_native_exporter"] for option in form["target_options"])
    assert all(not option["commercial_game_import_allowed"] for option in form["source_options"])
    assert json.loads(json.dumps(form)) == form


def test_editor_search_discovers_abandoned_regional_and_arcade_targets():
    obscure = editor_platform_options(search="laseractive", as_source=True)
    assert [item["id"] for item in obscure] == ["pioneer_laseractive"]
    handheld = editor_platform_options(search="wonderswan", kind="handheld", legacy=True)
    assert {item["id"] for item in handheld} == {"bandai_wonderswan", "bandai_wonderswan_color"}
    assert editor_platform_options(verified_native_only=True) == ()
    with pytest.raises(PlatformRegistryError):
        editor_platform_options(kind="made_up")
    with pytest.raises(PlatformRegistryError):
        editor_platform_options(search="x" * 129)
    with pytest.raises(PlatformRegistryError):
        editor_platform_options(legacy="yes")


def test_every_platform_can_be_original_design_basis_and_port_planning_target():
    registry = default_registry()
    for basis_id in ("nec_pc_fx", "funtech_super_acan", "tic80_fantasy", "commodore_64"):
        result = editor_portability_context(basis_id)
        assert result["possible_destination_count"] == len(registry.profiles)
        assert result["native_export_destination_count"] == 0
        assert len({x["target_platform_id"] for x in result["targets"]}) == len(registry.profiles)
        assert all(x["design_reachable"] and not x["native_export_verified"] for x in result["targets"])


def test_original_solvable_world_can_export_real_native_desktop_game_source(tmp_path):
    intent = GameBuildIntent(
        project_id="native-game", title='Original "Ink" \\ Maze', subtitle="Native SDL2",
        seed=102, width=11, height=11, levels=1, collectibles_per_level=1,
        hazards_per_level=1, theme="arcade",
    )
    world = generate_playable_world(intent, authorized=True)
    source = original("native-game", "bandai_wonderswan")
    first = compile_native_desktop(world, source, "windows_modern", authorized=True)
    again = compile_native_desktop(world, source, "windows_modern", authorized=True)
    assert first == again
    assert first.output_kind == "native_sdl2_source_project"
    assert not first.binary_verified
    assert "#include <SDL.h>" in first.game_c
    assert "SDL_CreateWindow" in first.game_c
    assert "SDL_GameController" in first.game_c
    assert "static void walk(int dx, int dy)" in first.game_c
    assert "add_executable(skeleton_homebrew game.c)" in first.cmake_lists
    assert "Original" in first.game_c and "Ink" in first.game_c
    assert "test</script>" not in first.game_c
    manifest = json.loads(first.manifest_json)
    assert manifest["world_digest"] == world.digest
    assert manifest["executable_built"] is False
    assert manifest["compiler_required"] is True
    assert manifest["releasable"] is False
    written = export_native_desktop_source(first, tmp_path / "native", authorized=True)
    assert {p.name for p in written.iterdir()} == {"game.c", "CMakeLists.txt", "manifest.json"}
    assert (written / "game.c").read_text() == first.game_c
    with pytest.raises(FileExistsError):
        export_native_desktop_source(first, written, authorized=True)


def test_native_desktop_export_is_rights_bound_and_platform_specific():
    world = generate_playable_world(GameBuildIntent(
        project_id="game-42", title="Safe Game", subtitle="Test", seed=42,
        width=9, height=9, levels=1, collectibles_per_level=1, hazards_per_level=0,
    ), authorized=True)
    source = original("game-42", "msx1")
    for target in ("linux_desktop", "macos_modern"):
        project = compile_native_desktop(world, source, target, authorized=True)
        assert project.target_platform_id == target
        assert "SDL_Init" in project.game_c
    with pytest.raises(NativeDesktopExportError):
        compile_native_desktop(world, source, "nintendo_famicom", authorized=True)
    with pytest.raises(NativeDesktopExportError):
        compile_native_desktop(world, original(), "linux_desktop", authorized=True)
    with pytest.raises(PermissionError):
        compile_native_desktop(world, source, "windows_modern", authorized=False)


def test_native_desktop_exports_a_exact_three_level_replay_without_html() -> None:
    intent = GameBuildIntent(
        project_id="native-acceptance", title="Original Star Routes",
        subtitle="Real C replay", seed=71368, width=17, height=15,
        levels=3, collectibles_per_level=3, hazards_per_level=5,
        starting_health=4, theme="space",
    )
    world = generate_playable_world(intent, authorized=True)
    source = original("native-acceptance", "bandai_wonderswan")
    project = compile_native_desktop(world, source, "linux_desktop", authorized=True)
    c = project.game_c
    manifest = json.loads(project.manifest_json)
    assert c.count("static int verify_replay(void)") == 1
    assert 'strcmp(argv[1], "--verify-replay")' in c
    assert "SKELETON_NATIVE_REPLAY_OK" in c
    assert "static const char *const verification_routes[LEVEL_COUNT]" in c
    assert not any(token in c for token in (
        "__REPLAY_DATA__", "__REPLAY_STEPS__", "__REPLAY_SCORE__", "__LEVEL_COUNT__",
    ))
    assert "SDL_CreateWindow" in c and "<html" not in c
    expected_steps = sum(len(level.safe_solution) for level in world.levels)
    assert manifest["native_replay_expected_steps"] == expected_steps
    assert manifest["native_replay_expected_score"] == 3 * (100 + 10 * 3)
    assert manifest["native_headless_replay_available"] is True
    assert manifest["native_headless_replay_executed"] is False
    assert manifest["executable_built"] is False
    # Source generation is not gameplay execution, binary verification or release approval.
    assert not project.binary_verified
    assert not manifest["releasable"]


def test_editor_distinguishes_real_native_source_generation_from_certified_binaries():
    form = editor_platform_form()
    assert form["native_source_project_destinations"] == [
        "linux_desktop", "macos_modern", "windows_modern",
    ]
    assert form["source_export_status"] == "three_desktop_c11_source_exporters_unverified_binaries"
    assert form["export_status"] == "no_native_target_verified"
    native = {option["id"]: option for option in form["target_options"]}
    for target in form["native_source_project_destinations"]:
        option = native[target]
        assert option["native_source_project_available"] is True
        assert option["native_source_project_kind"] == "sdl2_c11_cmake"
        assert option["capability_status"] == "native_source_project_only"
        assert not option["native_binary_built"]
        assert not option["verified_native_exporter"]
    for target in ("nec_pc_fx", "bandai_wonderswan", "funtech_super_acan"):
        assert native[target]["capability_status"] == "design_catalogue_only"
        assert native[target]["native_source_project_available"] is False
        assert native[target]["native_source_project_kind"] is None
    route = editor_portability_context("nec_pc_fx")
    assert route["native_source_project_destination_count"] == 3
    assert route["native_export_destination_count"] == 0
    assert sum(option["native_source_project_available"] for option in route["targets"]) == 3
