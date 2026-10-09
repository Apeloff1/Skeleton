"""Archive census, MAME metadata-only ingestion and evolutionary campaign tests."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.evolution_practice import practice_evolution_games, MAX_PRACTICE_STAGES
from skeleton.ai.game_builder.archive_import import (
    MachineArchiveError, import_mame_listxml, export_review_queue,
)
from skeleton.ai.game_builder.evolution_archive import (
    GameEvolutionError, archive_coverage_report,
    default_evolution_archive, parse_evolution_archive, plan_evolution_campaign,
)
from skeleton.ai.game_builder.platform_registry import default_registry
from skeleton.ai.game_builder.port_planner import HomebrewSource

MAME_XML = b'''<?xml version="1.0"?>
<!DOCTYPE mame [
<!ELEMENT mame (machine+)>
<!ELEMENT machine (description, year?, manufacturer?, input?, display*, driver?)>
]>
<mame build="0.289" mameconfig="10">
 <machine name="pioneer" sourcefile="src/mame/example.cpp">
  <description>Documented machine candidate</description>
  <year>1989</year><manufacturer>Example Lab</manufacturer>
  <display type="vector"/><input players="2"/><driver status="imperfect"/>
  <rom name="commercial-game-not-copied" sha1="DO-NOT-COPY" />
 </machine>
 <machine name="pioneer2" cloneof="pioneer" romof="pioneer">
  <description>Documented machine candidate (regional)</description>
  <year>1989</year><display type="raster"/>
 </machine>
 <machine name="z80" isdevice="yes" runnable="no"><description>CPU Z80</description></machine>
 <machine name="bootrom" isbios="yes" runnable="no"><description>BIOS root</description></machine>
</mame>'''


def homebrew(platform: str) -> HomebrewSource:
    return HomebrewSource(
        project_id="fresh-evolution-game",
        platform_id=platform,
        rights_basis="project_owned",
        evidence_sha256="a" * 64,
        creative_identity=("authored mechanics", "original character silhouettes", "distinctive palette"),
    )


def test_archive_catalog_expanded_without_equating_completeness_to_number():
    report = archive_coverage_report()
    assert report["catalogued_platform_records"] >= 500
    assert report["dated_evolution_example_records"] >= 75
    assert report["undated_or_unlinked_catalogue_records"] > 0
    assert report["historical_universe_denominator"] is None
    assert report["complete_historical_census"] is False
    assert report["independent_record_level_references_verified"] == 0
    assert report["native_platform_toolchains_verified"] == 0
    for name in (
        "henry_videosport_mk2", "apf_imagination_machine", "amstrad_gx4000",
        "soviet_vector_06c", "yugoslav_galaksija", "polish_elwro_800_junior",
        "pioneer_laseractive", "milton_bradley_microvision", "arcade_sega_system32",
        "arcade_namco_system21", "arcade_capcom_cps3", "nextcube",
    ):
        assert default_registry().get(name).id == name


def test_mame_metadata_census_never_imports_rom_names_or_promotes_toolchains(tmp_path):
    src = tmp_path / "machines.xml"
    src.write_bytes(MAME_XML)
    snapshot = import_mame_listxml(src)
    assert len(snapshot.records) == 4
    assert snapshot.source_sha256 == sha256(MAME_XML).hexdigest()
    assert [r.key for r in snapshot.records] == ["bootrom", "pioneer", "pioneer2", "z80"]
    assert [r.key for r in snapshot.records if r.archive_candidate] == ["pioneer", "pioneer2"]
    report = snapshot.summary()
    assert report["runnable_candidate_records"] == 2
    assert report["devices_bios_and_nonrunnable"] == 2
    assert report["automatic_promotions"] == 0
    assert report["native_builds_verified"] == 0
    assert snapshot.records[1].display_types == ("vector",)
    assert snapshot.records[1].input_players == 2
    dest = tmp_path / "review.jsonl"
    export_review_queue(snapshot, dest, limit=2, authorized=True)
    lines = [json.loads(s) for s in dest.read_text().splitlines()]
    assert len(lines) == 2
    assert all(l["may_auto_promote_to_platform"] is False for l in lines)
    assert all(l["native_toolchain_available"] is False for l in lines)
    assert "commercial-game-not-copied" not in dest.read_text()
    assert "DO-NOT-COPY" not in dest.read_text()
    with pytest.raises(FileExistsError):
        export_review_queue(snapshot, dest, authorized=True)
    with pytest.raises(PermissionError):
        export_review_queue(snapshot, tmp_path / "other.jsonl", authorized=False)


@pytest.mark.parametrize("xml", [
    MAME_XML.replace(b'name="pioneer2"', b'name="pioneer"'),
    MAME_XML.replace(b"<mame ", b"<notmame ").replace(b"</mame>", b"</notmame>"),
    MAME_XML.replace(b"</mame>", b""),
    MAME_XML.replace(b'<!ELEMENT machine', b'<!ENTITY exploit "data"><!ELEMENT machine'),
    MAME_XML.replace(b'name="pioneer"', b'name="../pioneer"'),
    b"<mame></mame>",
])
def test_mame_import_rejects_malformed_dangerous_or_duplicate_records(tmp_path, xml):
    src = tmp_path / "invalid.xml"
    src.write_bytes(xml)
    with pytest.raises(MachineArchiveError):
        import_mame_listxml(src)


def test_mame_import_has_hard_input_count_and_size_limits(tmp_path):
    src = tmp_path / "machines.xml"
    src.write_bytes(MAME_XML)
    with pytest.raises(MachineArchiveError):
        import_mame_listxml(src, maximum_bytes=10)
    with pytest.raises(MachineArchiveError):
        import_mame_listxml(src, maximum_machines=2)
    with pytest.raises(MachineArchiveError):
        import_mame_listxml(src, maximum_machines=True)
    with pytest.raises(MachineArchiveError):
        import_mame_listxml(src, maximum_bytes=0)


def test_evolution_archive_is_chronological_and_has_multiple_real_eras():
    archive = default_evolution_archive()
    assert archive.summary()["historical_nodes"] >= 75
    assert len(archive.summary()["lineages"]) >= 17
    assert archive.summary()["global_archive_complete"] is False
    assert archive.get("nintendo_famicom").year == 1983
    assert archive.get("sony_ps5").year == 2020
    path = archive.progress("nintendo_famicom", "nintendo_switch_2")
    assert path[0].platform_id == "nintendo_famicom"
    assert path[-1].platform_id == "nintendo_switch_2"
    assert all(b.year > a.year for a, b in zip(path, path[1:]))
    assert tuple(reversed(path)) == archive.progress(
        "nintendo_switch_2", "nintendo_famicom", reverse=True
    )
    with pytest.raises(GameEvolutionError):
        archive.progress("sony_psp", "sony_ps5")
    with pytest.raises(GameEvolutionError):
        archive.progress("sony_ps5", "sony_ps5")


def test_evolution_campaign_preserves_homebrew_design_and_does_not_fake_games():
    camp = plan_evolution_campaign(homebrew("nintendo_famicom"), "nintendo_switch")
    assert len(camp.stages) >= 5
    assert camp.original_project_id == "fresh-evolution-game"
    assert camp.generated_games_count == 0
    assert camp.native_binaries_built == 0
    assert "deterministic_replay_on_target" in camp.requirements()
    assert all(s.mode == "enhanced" and not s.native_export_verified for s in camp.stages)
    assert all("authored mechanics" in s.retained_identity for s in camp.stages)
    assert any("analogue_input" in s.unlocked_design_signals for s in camp.stages)
    reverse = plan_evolution_campaign(
        homebrew("nintendo_switch"), "nintendo_famicom", reverse=True
    )
    assert all(s.mode == "reverse_constrained" for s in reverse.stages)
    assert reverse.stages[-1].to_platform == "nintendo_famicom"
    with pytest.raises(GameEvolutionError):
        plan_evolution_campaign(homebrew("sony_ps5"), "sega_dreamcast")


def test_archive_parser_rejects_time_travel_unknown_nodes_and_fake_verification():
    from importlib.resources import files
    raw = json.loads(
        files("skeleton.ai.game_builder").joinpath("evolution_lineages.json").read_text(encoding="utf-8")
    )
    for mutation in ("time_travel", "unknown", "self_parent", "unearned_verification", "dupe"):
        data = json.loads(json.dumps(raw))
        child = next(n for n in data["nodes"] if n["predecessor"] is not None)
        if mutation == "time_travel":
            child["first_year"] = 1955
        if mutation == "unknown":
            child["platform_id"] = "not_catalogued"
        if mutation == "self_parent":
            child["predecessor"] = child["platform_id"]
        if mutation == "unearned_verification":
            child["chronology_confidence"] = "historically_verified"
        if mutation == "dupe":
            data["nodes"].append(dict(child))
        with pytest.raises(GameEvolutionError):
            parse_evolution_archive(json.dumps(data))


def test_dated_evolution_campaign_produces_actual_solvable_original_game_worlds():
    original = generate_playable_world(
        GameBuildIntent(
            project_id="fresh-evolution-game", title="Original evolution platformer",
            subtitle="Cross-era practice", seed=5003, width=15, height=15,
            levels=3, collectibles_per_level=2, hazards_per_level=2, theme="space",
        ),
        authorized=True,
    )
    plan = plan_evolution_campaign(homebrew("nintendo_famicom"), "nintendo_switch")
    pack = practice_evolution_games(original, plan, authorized=True)
    assert len(pack.demos) == len(plan.stages)
    assert pack.status()["successful_deterministic_replays"] == len(plan.stages)
    assert pack.status()["console_roms_built"] == 0
    assert all(not p.native_binary_built for p in pack.demos)
    assert all(p.target_adapter_state == "concept_prototype_not_native" for p in pack.demos)
    assert len({p.game_world.digest for p in pack.demos}) == len(pack.demos)
    assert all(p.game_world.intent.project_id == original.intent.project_id for p in pack.demos)
    assert practice_evolution_games(original, plan, authorized=True) == pack


def test_evolution_gameplay_rejects_mismatched_and_overbudget_campaigns():
    original = generate_playable_world(
        GameBuildIntent(
            project_id="fresh-evolution-game", title="Original game",
            subtitle="Training", seed=3211, width=11, height=11,
            levels=1, collectibles_per_level=1, hazards_per_level=0,
        ),
        authorized=True,
    )
    plan = plan_evolution_campaign(homebrew("sony_playstation"), "sony_ps5")
    with pytest.raises(PermissionError):
        practice_evolution_games(original, plan, authorized=False)
    with pytest.raises(GameEvolutionError):
        practice_evolution_games(original, plan, authorized=True, maximum_stages=0)
    with pytest.raises(GameEvolutionError):
        practice_evolution_games(original, plan, authorized=True, maximum_stages=True)
    with pytest.raises(GameEvolutionError):
        practice_evolution_games(original, replace(plan, original_project_id="wrong-project"), authorized=True)
    with pytest.raises(GameEvolutionError):
        practice_evolution_games(original, plan, authorized=True, maximum_stages=2)


def test_preconsole_archive_preserves_category_and_first_year_without_fake_emulator():
    registry = default_registry()
    assert len(registry.profiles) >= 520
    patent = registry.get("crt_amusement_device_1947")
    assert patent.kind == "precursor"
    assert patent.archive_disposition == "patent_concept"
    assert patent.first_year_candidate == 1947
    assert patent.verified_for_native_export is False
    ancient = registry.get("gottlieb_baffle_ball")
    assert ancient.kind == "mechanical"
    assert ancient.first_year_candidate == 1931
    arcade = registry.get("sega_periscope_em")
    assert arcade.kind == "electromechanical"
    assert arcade.preset == "em_arcade"
    archive = default_evolution_archive()
    assert archive.get("gottlieb_baffle_ball").year == 1931
    assert archive.get("atari_arcade_pong").year == 1972
    assert tuple(n.platform_id for n in archive.progress(
        "atari_arcade_pong", "atari_home_pong",
    )) == ("atari_arcade_pong", "atari_home_pong")


def test_ancient_mechanical_game_can_inspire_rights_cleared_modern_design():
    from skeleton.ai.game_builder.port_planner import PortMode, PortRequest, compile_port
    source = homebrew("gottlieb_baffle_ball")
    blueprint = compile_port(PortRequest((source,), "windows_modern", PortMode.ENHANCED))
    assert "visual_upgrade" in {a.phase for a in blueprint.actions}
    assert "simulation_upgrade" in {a.phase for a in blueprint.actions}
    assert blueprint.native_build_verified is False
    assert blueprint.releasable is False
