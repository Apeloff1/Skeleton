import pytest

from skeleton.frontier.biotope import (
    BiotopeMastery,
    BiotopeProgress,
    BiotopeSpec,
    BiotopeStageSpec,
    biotope_from_record,
    biotope_unlock_requirements,
    enter_stage,
    initial_biotope_progress,
    mastery_bonuses,
    record_biotope_catch,
    set_favorite_biotope,
    stage_from_record,
    stage_unlock_requirements,
    unlock_biotope,
    unlock_stage,
    unlockable_biotopes,
    unlockable_stages,
    weather_multiplier,
)


def _progress() -> BiotopeProgress:
    return initial_biotope_progress(
        starter_biotope_id="freshwater_lake",
        starter_stage_id="pond",
    )


def _saltwater() -> BiotopeSpec:
    return BiotopeSpec(
        id="saltwater",
        name="Salt Sea",
        salinity="high",
        environments=("open_ocean", "coral_reef"),
        best_times=("dawn", "dusk"),
        weather_effects={"storm": 1.5, "clear": 1.0},
        unlock_level=15,
        required_boat=True,
    )


def _coastal() -> BiotopeStageSpec:
    return BiotopeStageSpec(
        id="coastal_shallows",
        name="Coastal Shallows",
        biotope_id="saltwater",
        stage_number=1,
        unlock_level=15,
        difficulty=2,
        fish_pool=("sea_bass", "flounder"),
        rare_pool=("bonefish",),
    )


def test_source_records_normalize_without_promoting_catalogs():
    biotope = biotope_from_record(
        {
            "id": "saltwater",
            "name": "Salt Sea",
            "salinity": "high",
            "environments": ["open_ocean", "coral_reef"],
            "best_times": ["dawn", "dusk"],
            "weather_effects": {"storm": 1.5, "clear": 1.0},
            "unlock_level": 15,
            "required_boat": True,
            "description": "catalog-owned",
        }
    )
    stage = stage_from_record(
        {
            "id": "coastal_shallows",
            "name": "Coastal Shallows",
            "biotope": "saltwater",
            "stage_number": 1,
            "unlock_level": 15,
            "difficulty": 2,
            "fish_pool": ["sea_bass", "flounder"],
            "rare_pool": ["bonefish"],
            "legendary_pool": [],
            "description": "catalog-owned",
        }
    )

    assert biotope.id == "saltwater"
    assert biotope.required_boat is True
    assert biotope.weather_effects["storm"] == 1.5
    assert stage.biotope_id == "saltwater"
    assert stage.fish_pool == ("sea_bass", "flounder")


def test_declared_boat_requirement_is_enforced_for_unlock():
    progress = _progress()
    saltwater = _saltwater()

    assert biotope_unlock_requirements(
        saltwater, progress, user_level=15, has_boat=False
    ) == ("boat",)
    assert biotope_unlock_requirements(
        saltwater, progress, user_level=14, has_boat=False
    ) == ("level:15", "boat")

    plan = unlock_biotope(
        progress,
        saltwater,
        user_level=15,
        has_boat=True,
        first_stage=_coastal(),
    )
    assert "saltwater" in plan.progress.unlocked_biotopes
    assert "coastal_shallows" in plan.progress.unlocked_stages
    assert plan.auto_unlocked_stage_id == "coastal_shallows"


def test_auto_first_stage_cannot_bypass_declared_stage_level():
    too_high = BiotopeStageSpec(
        "coastal_shallows",
        "Coastal",
        "saltwater",
        1,
        20,
        2,
    )
    with pytest.raises(ValueError, match="first stage requires level 20"):
        unlock_biotope(
            _progress(),
            _saltwater(),
            user_level=15,
            has_boat=True,
            first_stage=too_high,
        )


def test_stage_unlock_requires_parent_biotope_and_level_then_can_enter():
    stage = BiotopeStageSpec(
        "coral_reef",
        "Coral Reef",
        "saltwater",
        2,
        25,
        3,
    )
    progress = _progress()
    assert stage_unlock_requirements(stage, progress, user_level=25) == ("biotope:saltwater",)

    progress = unlock_biotope(
        progress,
        _saltwater(),
        user_level=25,
        has_boat=True,
        first_stage=_coastal(),
    ).progress
    assert stage_unlock_requirements(stage, progress, user_level=24) == ("level:25",)
    unlocked = unlock_stage(progress, stage, user_level=25).progress
    entered = enter_stage(unlocked, stage)
    assert entered.current_biotope == "saltwater"
    assert entered.current_stage == "coral_reef"


def test_unlockable_queries_are_deterministic_and_reject_duplicate_specs():
    progress = _progress()
    saltwater = _saltwater()
    river = BiotopeSpec(
        "river",
        "River",
        "none",
        ("rapids",),
        ("morning",),
        {"rain": 1.5},
        8,
    )
    assert [item.id for item in unlockable_biotopes(
        (saltwater, river), progress, user_level=15, has_boat=False
    )] == ["river"]
    with pytest.raises(ValueError, match="duplicate biotope spec id"):
        unlockable_biotopes((river, river), progress, user_level=15)

    pond_two = BiotopeStageSpec("shallow_lake", "Shallow Lake", "freshwater_lake", 2, 10, 2)
    assert unlockable_stages((pond_two,), progress, user_level=10) == (pond_two,)


def test_mastery_bonus_formula_matches_source_exactly():
    bonuses = mastery_bonuses(10)
    assert bonuses.catch_rate == pytest.approx(1.2)
    assert bonuses.rare_chance == pytest.approx(1.3)
    assert bonuses.xp_multiplier == pytest.approx(1.1)
    assert bonuses.coin_multiplier == pytest.approx(1.15)


def test_large_xp_award_advances_multiple_levels_deterministically():
    result = record_biotope_catch(_progress(), "freshwater_lake", xp_earned=600)
    assert result.levels_gained == 3
    assert result.mastery == BiotopeMastery(level=4, xp=0, catches=1)

    second = record_biotope_catch(result.progress, "freshwater_lake", xp_earned=450)
    assert second.levels_gained == 1
    assert second.mastery == BiotopeMastery(level=5, xp=50, catches=2)


def test_mastery_state_rejects_unapplied_threshold_xp():
    with pytest.raises(ValueError, match="below the current level threshold"):
        BiotopeMastery(level=2, xp=200)


def test_weather_effects_are_explicit_and_unknown_weather_is_neutral():
    saltwater = _saltwater()
    assert weather_multiplier(saltwater, "storm") == 1.5
    assert weather_multiplier(saltwater, "fog") == 1.0


def test_favorite_biotope_must_be_unlocked():
    progress = set_favorite_biotope(_progress(), "freshwater_lake")
    assert progress.favorite_biotope == "freshwater_lake"
    with pytest.raises(ValueError, match="must be unlocked"):
        set_favorite_biotope(progress, "saltwater")


def test_stage_rarity_pools_cannot_overlap_and_strings_are_not_sequences():
    with pytest.raises(ValueError, match="must not overlap"):
        BiotopeStageSpec(
            "bad",
            "Bad",
            "river",
            1,
            1,
            1,
            fish_pool=("trout",),
            rare_pool=("trout",),
        )
    with pytest.raises(TypeError, match="sequence"):
        biotope_from_record(
            {
                "id": "river",
                "name": "River",
                "environments": "rapids",
                "best_times": [],
                "weather_effects": {},
                "unlock_level": 1,
            }
        )
