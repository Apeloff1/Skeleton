from datetime import datetime, timezone

from skeleton.frontier.cooking import ActiveCookingBuff
from skeleton.frontier.cooking_adapters import (
    catch_bonuses_from_cooking_buff,
    energy_booster_from_cooking_buff,
)


def test_cooking_buff_projects_into_existing_energy_and_catch_primitives():
    buff = ActiveCookingBuff(
        recipe_id="koi_hotpot",
        name="Golden Koi Hotpot",
        effects={
            "energy_restore": 100,
            "all_catch_bonus": 1.3,
            "rare_fish_bonus": 1.2,
            "legendary_bonus": 1.5,
            "coin_bonus": 1.5,
        },
        expires_at=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc),
    )

    energy = energy_booster_from_cooking_buff(buff)
    assert energy is not None
    assert energy.id == "cooking:koi_hotpot:energy"
    assert energy.energy_restore == 100

    catch = catch_bonuses_from_cooking_buff(buff)
    assert catch.catch_rate == 1.3
    assert catch.rare_chance == 1.2
    assert catch.legendary_chance == 1.5
    assert catch.coin_multiplier == 1.5


def test_cooking_buff_without_energy_restoration_does_not_invent_one():
    buff = ActiveCookingBuff(
        recipe_id="xp_dish",
        name="XP Dish",
        effects={"xp_bonus": 1.1},
        expires_at=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc),
    )
    assert energy_booster_from_cooking_buff(buff) is None
    assert catch_bonuses_from_cooking_buff(buff).xp_multiplier == 1.1
