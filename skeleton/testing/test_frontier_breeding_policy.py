from datetime import datetime, timedelta, timezone
import pytest
from skeleton.frontier.breeding import *

class FixedRng:
    def __init__(self, randoms=None, choices=None, uniform_value=1.0):
        self.randoms=list(randoms or [])
        self.choices=list(choices or [])
        self.uniform_value=uniform_value
    def random(self):
        return self.randoms.pop(0) if self.randoms else 0.9
    def choice(self, values):
        if self.choices:
            value=self.choices.pop(0)
            assert value in values
            return value
        return values[0]
    def uniform(self, lower, upper):
        assert lower <= self.uniform_value <= upper
        return self.uniform_value

def species():
    return {
      "bass": FishSpeciesSpec("bass", 40, 3, ("perch","pike","koi")),
      "koi": FishSpeciesSpec("koi", 200, 8, ("carp","goldfish","bass")),
    }

def parents():
    return (
      BreedingParent("a","bass",{"color":"red","rarity_gene":"common","size_gene":"medium"},50),
      BreedingParent("b","koi",{"color":"blue","rarity_gene":"rare","size_gene":"large"},70),
    )

def test_start_and_refresh():
    a,b=parents()
    now=datetime(2026,9,15,tzinfo=timezone.utc)
    job=start_breeding(a,b,parent1_slot=0,parent2_slot=1,species=species(),now=now)
    assert job.complete_at==now+timedelta(hours=8)
    assert refresh_breeding(job, now+timedelta(hours=7)).status=="breeding"
    done=refresh_breeding(job, now+timedelta(hours=8))
    assert done.status=="complete"
    with pytest.raises(ValueError):
        start_breeding(a,b,parent1_slot=0,parent2_slot=0,species=species(),now=now)

def test_traits_mutation_and_inheritance():
    domains={"color":["red","blue","gold"],"size_gene":["medium","large"],"rarity_gene":["common","rare"]}
    rng=FixedRng(randoms=[0.01,0.9,0.9], choices=["gold","large","common"])
    traits=generate_traits(domains, parents()[0].traits, parents()[1].traits, rng=rng)
    assert traits=={"color":"gold","size_gene":"large","rarity_gene":"common"}

def test_value_and_special():
    koi=species()["koi"]
    assert calculate_fish_value(koi,{"rarity_gene":"rare","size_gene":"large","color":"gold","pattern":"iridescent"})==1462
    special=special_breed_from_record({"id":"rainbow_bass","name":"Rainbow Bass","parents":["bass","koi"],"required_traits":{"color":"rainbow"},"rarity":"rare","value":300})
    assert matching_special_breed("bass","koi",{"color":"rainbow"},[special],rng=FixedRng())==special
    assert matching_special_breed("bass","koi",{"color":"red"},[special],rng=FixedRng(randoms=[0.01]))==special

def test_offspring_special_uses_special_value_and_discovery():
    a,b=parents()
    now=datetime(2026,9,15,tzinfo=timezone.utc)
    job=replace(start_breeding(a,b,parent1_slot=0,parent2_slot=1,species=species(),now=now), status="complete")
    special=SpecialBreedSpec("rainbow_bass","Rainbow Bass",("bass","koi"),{"color":"rainbow"},"rare",300)
    domains={"color":["rainbow"],"rarity_gene":["common"],"size_gene":["medium"],"pattern":["solid"]}
    # Mutate color to the required special trait, inherit remaining traits, then choose species.
    rng=FixedRng(randoms=[0.01,0.9,0.9,0.9], choices=["rainbow","common","medium","solid","bass"], uniform_value=1.0)
    out=offspring_plan(job,trait_domains=domains,species=species(),specials=[special],rng=rng,id_factory=lambda:"offspring-1",now=job.complete_at)
    assert out.special_breed_id=="rainbow_bass"
    assert out.is_new_discovery
    assert out.xp_reward==60
    assert out.value==1125  # 300 * rare 2.5 * rainbow-color 1.5
    assert out.size==60

def test_progress_can_cross_multiple_levels():
    p=BreedingProgress(level=1,xp=140,total_bred=2)
    special=SpecialBreedSpec("s","S",("bass","koi"),{}, "rare", 100)
    result=apply_breeding_reward(p,special_breed=special)
    assert result.level==2
    assert result.xp==50
    assert result.total_bred==3
    assert result.rare_discoveries==frozenset({"s"})

def test_speedup_and_slot_policy():
    a,b=parents()
    now=datetime(2026,9,15,tzinfo=timezone.utc)
    job=start_breeding(a,b,parent1_slot=0,parent2_slot=1,species=species(),now=now)
    assert speed_up_cost(job, now)==40
    assert speed_up_cost(job, job.complete_at+timedelta(hours=1))==5
    assert slot_upgrade_plan("breeding",2).gem_cost==400
    assert slot_upgrade_plan("parent",4).gem_cost==400
    with pytest.raises(ValueError):
        slot_upgrade_plan("breeding",4)

def test_strict_boundaries():
    with pytest.raises(TypeError):
        species_from_record("x",{"base_value":True,"breed_time_hours":1,"compatible":[]})
    with pytest.raises(ValueError):
        species_from_record("x",{"base_value":1,"breed_time_hours":float("nan"),"compatible":[]})
    with pytest.raises(ValueError):
        start_breeding(*parents(),parent1_slot=0,parent2_slot=1,species=species(),now=datetime(2026,9,15))
