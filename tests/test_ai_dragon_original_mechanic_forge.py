"""Executable functional-originality proofs for 16.7m+ original game nuclei."""
from __future__ import annotations
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
    SCHEMA,MECHANICS,MECHANIC_COUNT,MECHANIC_IDS,MECHANIC_LEVELS,
    PROGRAM_COUNT,MILLION_DISTINCT_ENABLE_PROFILES,
    encode_levels,decode_levels,make_program,program_from_levels,
    validate_program,initial,choices,perform,replay,prove_mechanic,
    distinguish,binary_nucleus,capabilities,
)


def test_actual_32_mechanic_generator_surpasses_quintillion_combinations():
    view=capabilities()
    assert view["schema"]==SCHEMA
    assert view["actual_mechanic_verbs"]==32
    assert view["levels_per_mechanic"]==4
    assert int(view["exact_original_rule_program_address_count"])==4**32
    assert PROGRAM_COUNT==18_446_744_073_709_551_616
    assert PROGRAM_COUNT>10**18
    assert view["mechanically_separable_binary_nuclei"]==2**24
    assert MILLION_DISTINCT_ENABLE_PROFILES==16_777_216
    assert view["possible_cross_mechanic_join_routes"]==16
    assert view["real_games_materialized_in_report"]==0
    assert view["finished_unique_cleared_games"]==0
    assert "not millions of completed" in view["not_claimed"]


@pytest.mark.parametrize("idx",[
    0,1,3,4,42,1977,2**32,2**63,PROGRAM_COUNT-1,
])
def test_every_large_original_mechanic_index_roundtrips_exactly(idx):
    design=make_program(str(idx))
    assert int(design.decimal_index)==idx
    assert design.intensities==decode_levels(idx)
    assert encode_levels(design.intensities)==idx
    assert program_from_levels(design.intensities)==design
    assert not design.is_finished_game
    validate_program(design)
    assert len(design.source_digest)==64


@pytest.mark.parametrize("n",[
    0,1,2,3,42,2026,1_000_000,2**23,
    MILLION_DISTINCT_ENABLE_PROFILES-1,
])
def test_each_of_16m_original_binary_nuclei_decodes_to_its_real_action_mask(n):
    program=binary_nucleus(n)
    assert all(x in (0,1) for x in program.intensities)
    assert all(x==0 for x in program.intensities[24:])
    got=sum((program.intensities[i]<< (23-i)) for i in range(24))
    assert got==n
    assert binary_nucleus(n)==program
    actions=choices(program,initial(program))
    for i in range(24):
        action=actions[i]
        assert action["id"]=="practice_"+MECHANIC_IDS[i]
        assert action["available"]==bool(n&(1<<(23-i)))
    assert sum(x["available"] for x in actions[:24])==n.bit_count()


@pytest.mark.parametrize("level",[1,2,3])
@pytest.mark.parametrize("axis",range(32))
def test_each_authored_mechanic_changes_actual_player_resources_world_and_history(
    axis,level,
):
    pattern=[0]*MECHANIC_COUNT
    pattern[axis]=level
    world=program_from_levels(tuple(pattern))
    options=choices(world,initial(world))
    assert len([x for x in options if x["id"].startswith("practice_")])==32
    assert options[axis]["available"]
    example=prove_mechanic(world,axis)
    assert example["available"]
    assert example["axis"]==MECHANIC_IDS[axis]
    assert example["level"]==level
    assert example["mastery_after"]==level
    assert example["world_evolution_after"]>=2*level
    assert example["cost"]>0
    assert example["gain"]>0
    assert len(example["witness"])==64
    action="practice_"+MECHANIC_IDS[axis]
    future=replay(world,(action,))
    assert future.mastery[axis]==level
    assert future.domain_evolution[axis]==example["world_evolution_after"]
    assert future.turn==1
    assert future.history_digest==example["witness"]
    assert future.changed_places
    assert replay(world,(action,))==future
    if axis in (23,24):
        assert future.endings
    if axis in (25,31):
        assert future.era>0
    if axis in (10,13):
        assert future.realm>0


@pytest.mark.parametrize("axis",range(32))
def test_mutating_any_mechanic_level_is_detectably_distinct_in_real_gameplay(axis):
    base=[0]*32
    base[axis]=1
    level1=program_from_levels(tuple(base))
    base[axis]=2
    level2=program_from_levels(tuple(base))
    base[axis]=3
    level3=program_from_levels(tuple(base))
    base[axis]=0
    level0=program_from_levels(tuple(base))
    absent=distinguish(level0,level1)
    assert absent["distinguishable"] and absent["axis_index"]==axis
    assert absent["reason"]=="different_action_availability"
    first=distinguish(level1,level2)
    second=distinguish(level2,level3)
    assert first["distinguishable"] and second["distinguishable"]
    assert first["axis_index"]==second["axis_index"]==axis
    assert first["reason"]=="different_executable_cost_rewards_and_world_progress"
    assert first["left"]["mastery_after"]==1
    assert first["right"]["mastery_after"]==2
    assert second["left"]["world_evolution_after"]!=second["right"]["world_evolution_after"]


def test_two_unrelated_binary_nuclei_have_different_actually_playable_actions():
    for before,after in (
        (0,1),(0,2),(1,2),(24,25),(12345,12346),
        (MILLION_DISTINCT_ENABLE_PROFILES-2,
         MILLION_DISTINCT_ENABLE_PROFILES-1),
    ):
        old=binary_nucleus(before)
        updated=binary_nucleus(after)
        evidence=distinguish(old,updated)
        assert evidence["distinguishable"]
        assert old.source_digest!=updated.source_digest
        assert choices(old,initial(old))!=choices(updated,initial(updated))


def test_original_mechanic_synergy_requires_both_executed_actions_not_metadata():
    data=[0]*32
    data[6]=2
    data[7]=3
    design=program_from_levels(tuple(data))
    before=initial(design)
    action="join_rotating_corridors_doubleback_caches"
    assert not next(x for x in choices(design,before) if x["id"]==action)["available"]
    after_first=perform(design,before,"practice_rotating_corridors")
    assert not next(x for x in choices(design,after_first) if x["id"]==action)["available"]
    after_both=perform(design,after_first,"practice_doubleback_caches")
    assert next(x for x in choices(design,after_both) if x["id"]==action)["available"]
    linked=perform(design,after_both,action)
    assert linked.era==after_both.era+1
    assert linked.x==after_both.x+1
    assert linked.unlocked_joins==(action,)
    assert linked.history_digest!=after_both.history_digest
    with pytest.raises(ValueError):
        perform(design,before,action)


def test_real_performing_world_changes_does_not_rely_on_fixed_mandatory_win():
    data=[0]*32
    for i in (8,16,23,24,25,30,31):data[i]=2
    program=program_from_levels(tuple(data))
    actions=(
        "practice_scenic_detours",
        "practice_settlement_growth",
        "practice_branching_chronicles",
        "practice_alternate_conclusions",
        "practice_postgame_repair",
        "practice_terrain_terraforming",
        "practice_world_era_cycles",
    )
    after=replay(program,actions)
    assert after.turn==7
    assert len(after.changed_places)==7
    assert after.era>=4
    assert after.endings
    assert after.mastery[24]==2
    assert after.mastery[25]==2
    assert after.mastery[30]==2
    assert replay(program,actions)==after


def test_genomic_parent_codex_link_is_verified_and_modification_changes_source():
    left=make_program(str(PROGRAM_COUNT-1),parent_codex_index="0")
    unparented=make_program(str(PROGRAM_COUNT-1))
    validate_program(left)
    assert left.source_digest!=unparented.source_digest
    assert left.parent_codex_digest
    assert left.parent_codex_index=="0"
    with pytest.raises(ValueError):
        validate_program(replace(left,parent_codex_index="1"))
    assert distinguish(left,unparented)["distinguishable"] is False


@pytest.mark.parametrize("value",[
    "-1","00","01","1.0","1e19",str(PROGRAM_COUNT),
    str(PROGRAM_COUNT+1),None,True,
])
def test_noncanonical_or_out_of_range_quintillion_mechanic_addresses_are_denied(value):
    with pytest.raises(ValueError):
        make_program(value)


@pytest.mark.parametrize("values",[
    (), (0,)*31, (0,)*33,(0,)*31+(4,),
    (0,)*31+(-1,),(0,)*31+(True,),
])
def test_invalid_original_mechanic_vectors_are_rejected(values):
    with pytest.raises(ValueError):
        program_from_levels(values)


def test_world_source_digest_and_actions_must_be_exact_to_prevent_forged_output():
    design=binary_nucleus(1234567)
    with pytest.raises(ValueError):
        validate_program(replace(design,source_digest="x"*64))
    with pytest.raises(ValueError):
        validate_program(replace(design,is_finished_game=True))
    with pytest.raises(ValueError):
        replay(design,("not_a_real_gameplay_verb",))
    with pytest.raises(ValueError):
        replay(design,("rest_world",)*129)
