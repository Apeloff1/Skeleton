"""Generational world codex and real gate-level progression."""
from __future__ import annotations
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_world_codex import (
    SCHEMA,DOMAIN_AXIS,DOMAINS,AXIS_NAMES,AXIS_INDEX,
    WorldCodex,CODEX_GENOMES,CODEX_WORLD_ADDRESSES,
    decode,encode,unrank,rank,edit,validate,summary,
)
from skeleton.ai.webcrawler.dragon_world_codex_runtime import (
    GATE_MODES,GATE_VECTORS,
    start,step,replay,witness_to_gate,proof_of_access,
    available_actions,gate_catalog,codex_cell,report,
)
from skeleton.ai.webcrawler.dragon_codex_platforms import (
    COHORTS,cohort,compile_content,content_pack,verify_content_pack,
    target_preview,
)
from skeleton.ai.webcrawler.dragon_native_targets import CATALOG


def test_hypergenome_contains_128_actual_256_step_attributes_and_exact_huge_count():
    assert len(DOMAINS)==16 and len(AXIS_NAMES)==128
    assert len(set(AXIS_NAMES))==128
    assert all(len(DOMAIN_AXIS[d])==8 for d in DOMAINS)
    assert CODEX_GENOMES==256**128==2**1024
    assert CODEX_WORLD_ADDRESSES>10**340
    data=summary()
    assert data["axes"]==128
    assert data["levels_per_axis"]==256
    assert data["enumerated_games"]==0
    assert data["independently_reviewed_unique_games"]==0


@pytest.mark.parametrize("n",[
    0,1,255,256,257,2**64,2**255,
    2**512,2**1023,2**1024-1,
])
def test_1024_bit_genome_exact_roundtrip_with_no_unsafe_js_number(n):
    value=decode(n)
    assert encode(value)==n
    assert len(value.values)==128
    assert all(0<=x<256 for x in value.values)


@pytest.mark.parametrize("index",[
    "0","1","255",str(2**1024-1),
    str(2**1024),str(2**1030),
    str(CODEX_WORLD_ADDRESSES//2),
    str(CODEX_WORLD_ADDRESSES-1),
])
def test_entire_lazy_high_integer_codex_space_has_real_reversible_design(index):
    value=unrank(index)
    root,genes=validate(value)
    assert value.schema==SCHEMA
    assert value.decimal_index==index
    assert rank(value.parent_decimal_index,genes)==index
    assert genes.values==value.values
    assert not value.unique_published_game
    assert value.original_work_only
    assert root.genome_digest==value.parent_genome_digest


@pytest.mark.parametrize("bad",[
    "", "00","01","-1","+1","1e400","1.0"," 7","7 ",
    5,True,str(CODEX_WORLD_ADDRESSES),"9"*500,
])
def test_huge_codex_addresses_reject_float_rounding_and_noncanonical_inputs(bad):
    with pytest.raises(ValueError):
        unrank(bad)


def test_all_128_game_axes_can_be_edited_independently_and_regenerated():
    baseline=unrank("0")
    assert baseline.values==(0,)*128
    for index,axis in enumerate(AXIS_NAMES):
        changed=edit("0",{axis:255})
        assert changed.values[index]==255
        assert sum(changed.values)==255
        assert changed.codex_digest!=baseline.codex_digest
        assert changed.decimal_index==str(255*256**(127-index))
        assert unrank(changed.decimal_index)==changed


def test_real_128_study_actions_modify_distinct_world_history_and_progress():
    original=unrank("0")
    state=start(original)
    assert state.actions==0
    for i,axis in enumerate(AXIS_NAMES):
        moved=step(original,state,"study_"+axis)
        assert moved.axis_mastery[i]==1
        assert sum(moved.axis_mastery)==1
        assert moved.domain_reputation[i//8]>state.domain_reputation[i//8]
        assert moved.player.base.turn==1
        assert moved.history_digest!=state.history_digest
    # Same action with a different authored world rule produces changed
    # world pressure/reputation and source receipt, not just an ID.
    bigger=edit("0",{"choice_permanence":255})
    updated=step(bigger,start(bigger),"study_choice_permanence")
    basic=step(original,state,"study_choice_permanence")
    assert updated.domain_reputation[10]>basic.domain_reputation[10]
    assert updated.history_digest!=basic.history_digest


@pytest.mark.parametrize("domain",DOMAINS)
def test_each_of_16_delayed_routes_has_a_real_constructive_unlock_and_passage(domain):
    source=unrank(str(2**1024-1))
    witness=witness_to_gate(source,domain)
    assert witness
    completed=replay(source,witness)
    active=gate_catalog(source,completed)
    gateway=next(v for v in active if v["domain"]==domain)
    assert gateway["already_discovered"]
    assert gateway["earned"]
    assert gateway["mastery_current"][0]>=gateway["mastery_required"][0]
    assert gateway["mastery_current"][1]>=gateway["mastery_required"][1]
    assert completed.player.base.turn==len(witness)
    assert witness[-1]==gateway["name"]
    report=proof_of_access(source,domain)
    assert report["completed_non_mandatory_passage"]
    assert report["steps"]==len(witness)
    assert report["end_source_digest"]==completed.history_digest


def test_delayed_access_cannot_be_skipped_or_achieved_before_earnt_mastery():
    address=edit("0",{
        "elevation_tectonics":255,"plate_migration":255,
    })
    current=start(address)
    gate=gate_catalog(address,current)[0]
    assert not gate["available"]
    assert gate["reason"]=="mastery_locked"
    with pytest.raises(ValueError):
        step(address,current,gate["name"])
    current=step(address,current,"wait_world")
    assert not gate_catalog(address,current)[0]["available"]
    for _ in range(4):
        current=step(address,current,"study_elevation_tectonics")
        current=step(address,current,"study_plate_migration")
    gate=gate_catalog(address,current)[0]
    assert gate["earned"]
    for _ in range(32):
        if gate["available"]:break
        current=step(address,current,"wait_world")
        gate=gate_catalog(address,current)[0]
    assert gate["available"]
    arrived=step(address,current,gate["name"])
    assert (arrived.player.base.x,arrived.player.base.y)==(-2,-3)
    assert gate["name"] in arrived.journeys
    assert arrived.history_digest!=current.history_digest


def test_whole_world_is_allowed_to_have_no_win_while_delayed_paths_are_playable():
    result=report(unrank("0"),start(unrank("0")))
    assert result["no_mandatory_win"]
    assert result["current_turn"]==0
    assert len(result["available_actions"])==146
    assert len(result["gates"])==16
    assert all(not x["available"] for x in result["gates"])
    assert len(result["domain_progress"])==16
    assert len(result["terrain"]["codex_terrain"])==16


def test_varying_axis_values_really_change_actual_terrain_and_timing():
    calm=unrank("0")
    storm=edit("0",{
        "storm_fronts":255,"rain_seasons":224,
        "predator_pressure":160,"corridor_rotation":200,
    })
    before=codex_cell(calm,start(calm))
    after=codex_cell(storm,start(storm))
    assert before["codex_cell_digest"]!=after["codex_cell_digest"]
    assert before["codex_terrain"]["climate"]!=after["codex_terrain"]["climate"]
    assert gate_catalog(calm,start(calm))[2]["earliest_turn"]!=(
        gate_catalog(storm,start(storm))[2]["earliest_turn"])


def test_every_registered_console_gets_a_deterministic_honest_content_plan():
    addr=edit("0",{"volcanic_activity":255,"settlement_decay":245,
                   "world_repopulation":230,"story_branching":255})
    for target in CATALOG:
        plan=compile_content(addr,target)
        assert plan.target_id==target
        assert plan.original_axis_count==128
        assert 0<plan.active_axes<=128
        assert plan.active_axes+len(plan.deferred_axes)==128
        assert len(plan.chosen_axes)==len(plan.quantized_levels)
        assert max(plan.quantized_levels)<plan.level_buckets
        assert len(plan.active_route_gates)<=16
        assert set(plan.active_route_gates).isdisjoint(plan.deferred_route_gates)
        assert not plan.hardware_binary_compiled
        assert not plan.real_hardware_playtested
        assert not plan.final_platform_source_emitted
        assert plan.machine_width==CATALOG[target].max_width
        assert plan.machine_height==CATALOG[target].max_height


@pytest.mark.parametrize("target",[
    "atari_2600","game_boy","nes","snes","genesis",
    "ps1","nintendo_64","game_boy_advance","nintendo_ds",
    "psp","ps2","xbox_original","pc_linux","pc_windows",
])
def test_original_platform_world_chunks_are_real_content_not_fake_roms(target):
    if target not in CATALOG:
        pytest.skip("not in registered target catalog")
    addr=edit("0",{"volcanic_activity":255,"story_branching":128})
    pack=content_pack(addr,target,chunks=2)
    assert pack["native_binary"] is None
    assert not pack["ready_for_hardware_build"]
    assert len(pack["chunks"])==2
    assert pack["chunks"][0]["identity"]!=pack["chunks"][1]["identity"]
    assert verify_content_pack(addr,pack)["verified"]
    assert verify_content_pack(addr,pack)["room_count"]==(
        2*pack["projection"]["rooms_per_chunk"])
    assert pack==content_pack(addr,target,chunks=2)


def test_source_platform_projection_fails_closed_on_tampered_levels_and_chunks():
    source=unrank("0")
    pack=content_pack(source,"game_boy",chunks=2)
    altered={**pack,"content_sha256":"0"*64}
    with pytest.raises(ValueError):
        verify_content_pack(source,altered)
    with pytest.raises(ValueError):
        compile_content(source,"never_released_console")
    with pytest.raises(ValueError):
        content_pack(source,"game_boy",chunks=65)


def test_retro_and_pc_plans_degrade_transparently_to_actual_profile_budgets():
    source=edit("0",{"maze_mutation_frequency":250,"world_repopulation":255})
    if "game_boy" not in CATALOG or "pc_linux" not in CATALOG:
        pytest.skip("hardware catalog removed target")
    old=compile_content(source,"game_boy")
    modern=compile_content(source,"pc_linux")
    assert old.cohort=="tile_8_bit"
    assert modern.cohort=="desktop"
    assert old.active_axes<modern.active_axes
    assert old.level_buckets<modern.level_buckets
    assert old.rooms_per_chunk<modern.rooms_per_chunk
    assert old.deferred_axes
    assert old.toolchain!=modern.toolchain
    assert not modern.hardware_binary_compiled
