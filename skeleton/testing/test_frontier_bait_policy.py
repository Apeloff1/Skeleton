import pytest
from skeleton.frontier.bait import *

def worm():
    return bait_from_record({
        "id":"worm","name":"Common Worm","rarity":"common","durability":3,
        "cost":{"coins":10},"catch_bonus":1.0,"rare_bonus":1.0,
        "effective_fish":["minnow","perch","bass"],
    })

def storm():
    return bait_from_record({
        "id":"storm_bait","name":"Storm Bait","rarity":"rare","durability":4,
        "cost":{"coins":80},"catch_bonus":1.4,"rare_bonus":1.5,
        "storm_bonus":2.0,"effective_fish":["storm_fish","catfish"],
    })

def spot():
    return spot_from_record({
        "id":"ocean","name":"Deep Ocean","difficulty":4,"unlock_level":25,
        "bonuses":{"xp":1.8,"coins":1.5,"rare_chance":1.3},
        "requires_boat":True,
    })

def test_purchase_and_affordability():
    assert bait_purchase_cost(worm(),3)=={"coins":30}
    assert can_afford_cost({"coins":30},{"coins":30})
    assert not can_afford_cost({"coins":29},{"coins":30})
    with pytest.raises(TypeError):
        bait_purchase_cost(worm(), True)

def test_equip_and_use_depletes_without_negative_state():
    plan=equip_bait(BaitLoadout(), worm(), owned_quantity=1)
    assert plan.inventory_decrement==1
    state=plan.next_loadout
    for remaining in (2,1):
        use=use_bait(state,worm())
        assert use.bait_used
        assert not use.bait_depleted
        assert use.next_loadout.uses_remaining==remaining
        state=use.next_loadout
    final=use_bait(state,worm())
    assert final.bait_used
    assert final.bait_depleted
    assert final.next_loadout==BaitLoadout()

def test_empty_loadout_is_noop():
    use=use_bait(BaitLoadout(), None)
    assert not use.bait_used
    assert not use.bait_depleted
    assert use.catch_bonus==1.0

def test_source_bonus_aggregation_and_external_equipment_composition():
    base=calculate_catch_bonuses(storm(),spot(),is_storm=True)
    assert base.catch_rate==pytest.approx(2.8)
    assert base.rare_chance==pytest.approx(1.95)
    assert base.xp_multiplier==pytest.approx(1.8)
    combined=combine_external_bonuses(base,{"catch_rate":1.2,"rare_chance":1.1,"unknown":99})
    assert combined.catch_rate==pytest.approx(3.36)
    assert combined.rare_chance==pytest.approx(2.145)

def test_spot_unlock_requirements_and_selection():
    ocean=spot()
    assert spot_unlock_requirements(ocean,player_level=24)==("level:25","boat")
    assert can_unlock_spot(ocean,player_level=25,has_boat=True)
    assert spot_unlock_requirements(ocean,player_level=25,has_boat=True,unlocked_spots=["ocean"])==("already_unlocked",)
    assert select_spot("ocean",["pond","ocean"])=="ocean"
    with pytest.raises(ValueError):
        select_spot("reef",["pond"])

def test_required_item_policy():
    volcano=FishingSpotSpec("volcano","Volcano",5,50,requires_item="heat_suit")
    assert spot_unlock_requirements(volcano,player_level=50)==("item:heat_suit",)
    assert can_unlock_spot(volcano,player_level=50,inventory_items=["heat_suit"])

def test_effective_fish_and_all():
    assert bait_effective_for_fish(worm(),"bass")
    power=BaitSpec("power","Power","rare",5,effective_fish=("all",))
    assert bait_effective_for_fish(power,"anything")

def test_strict_jsonish_numeric_boundaries():
    with pytest.raises(ValueError):
        BaitSpec("x","X","rare",1,catch_bonus=float("nan"))
    with pytest.raises(TypeError):
        BaitLoadout("worm", True)
    with pytest.raises(TypeError):
        calculate_catch_bonuses(None,None,is_night=1)
