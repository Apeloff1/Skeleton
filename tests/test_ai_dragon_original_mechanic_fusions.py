"""1024 directed mechanics: actual gates, asymmetric world consequences."""
from __future__ import annotations

from dataclasses import replace
import pytest
from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
    MECHANIC_COUNT,DIRECTED_MECHANIC_FUSIONS,
    PROGRAM_COUNT,make_program,initial,perform,replay,
    interaction_catalog,
)


def _fully():
    return make_program(str(PROGRAM_COUNT-1))


def test_original_game_synthesizes_1024_mechanically_separate_pair_options_lazily():
    world=_fully()
    first=initial(world)
    whole=[]
    for offset in range(0,1024,64):
        page=interaction_catalog(world,first,offset=offset,limit=64)
        assert page["returned"]==64
        assert page["offset"]==offset
        assert page["total_possible_directed_fusions"]==1024
        whole.extend(page["interactions"])
    assert len(whole)==1024
    assert len({x["id"] for x in whole})==1024
    assert all(not x["available"] for x in whole)
    assert all(x["reason"]=="mastery_locked" for x in whole)
    assert whole[0]["id"]=="fusion_00_00"
    assert whole[-1]["id"]=="fusion_31_31"


@pytest.mark.parametrize("a,b",[
    (0,1),(1,0),(6,7),(7,6),(10,13),(13,10),
    (23,24),(24,23),(30,31),(31,30),(0,0),(31,31),
])
def test_earned_cross_mechanic_pair_is_executable_gameplay_with_real_world_effect(a,b):
    world=_fully()
    source=world.intensities[a]
    target=world.intensities[b]
    start=initial(world)
    first=perform(world,start,"practice_"+
                  __import__(
                    "skeleton.ai.webcrawler.dragon_original_mechanic_forge",
                    fromlist=["MECHANIC_IDS"],
                  ).MECHANIC_IDS[a])
    names=__import__(
        "skeleton.ai.webcrawler.dragon_original_mechanic_forge",
        fromlist=["MECHANIC_IDS"],
    ).MECHANIC_IDS
    action="fusion_"+str(a).zfill(2)+"_"+str(b).zfill(2)
    if a==b:
        ready=perform(world,first,"practice_"+names[a])
    else:
        ready=perform(world,first,"practice_"+names[b])
    page=interaction_catalog(world,ready,offset=a*32+b,limit=1)
    assert page["returned"]==1
    assert page["interactions"][0]["id"]==action
    assert page["interactions"][0]["available"]
    altered=perform(world,ready,action)
    assert altered.turn==ready.turn+1
    assert altered.era==ready.era+1
    assert altered.history_digest!=ready.history_digest
    assert action in altered.unlocked_joins
    assert altered.resources!=ready.resources
    assert altered.domain_evolution[a]>ready.domain_evolution[a]
    assert altered.domain_evolution[b]>ready.domain_evolution[b]
    assert altered.changed_places!=ready.changed_places
    assert replay(world,("practice_"+names[a],"practice_"+names[b],action)
                  if a!=b else
                  ("practice_"+names[a],"practice_"+names[a],action))==altered


def test_direction_matters_in_real_resource_and_geographic_world_changes():
    names=__import__(
        "skeleton.ai.webcrawler.dragon_original_mechanic_forge",
        fromlist=["MECHANIC_IDS"],
    ).MECHANIC_IDS
    world=_fully()
    prepared=replay(world,("practice_"+names[0],"practice_"+names[1]))
    forward=perform(world,prepared,"fusion_00_01")
    backward=perform(world,prepared,"fusion_01_00")
    assert forward!=backward
    assert forward.history_digest!=backward.history_digest
    assert (forward.x,forward.y)!=(backward.x,backward.y)
    assert forward.era==backward.era==prepared.era+1


def test_out_of_range_or_unearned_cross_mechanic_fusions_fail_closed():
    world=_fully()
    initial_state=initial(world)
    with pytest.raises(ValueError):
        perform(world,initial_state,"fusion_00_01")
    for illegal in ("fusion_32_32","fusion_99_00","fusion_-1_01",
                    "fusion_0_1","fusion_000_001","fusion_00_00_evil"):
        with pytest.raises(ValueError):
            perform(world,initial_state,illegal)
    for offset,limit in ((-1,2),(1024,1),(0,0),(0,65),
                         (True,10),(0,False)):
        with pytest.raises(ValueError):
            interaction_catalog(world,initial_state,offset=offset,limit=limit)
