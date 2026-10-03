import pytest

from core.eras import ERAS, ERA_ORDER
from core.vfx_combat_catalog import (
    CATALOG,
    CUE_TYPES,
    DURATION_WINDOWS_MS,
    FRAME_MS_60HZ,
    TELEGRAPH_LEAD_BASE_MS,
    TELEGRAPH_LEAD_SCALE_MS,
    TELEGRAPH_SHAPES,
    colors_ok,
    cue_for,
    duration_ok,
    emit,
    frame_budget,
    frame_budget_ok,
    min_telegraph_lead_ms,
    plan_frame,
    telegraph_for,
    telegraph_lead_ok,
    validate_catalog,
    validate_cue,
)
from core.vfx_cues import VfxState


def test_catalog_covers_every_era_and_cue_type():
    assert set(CATALOG) == set(ERAS)
    for era in ERA_ORDER:
        assert set(CATALOG[era]) == set(CUE_TYPES)
        for cue_type, cue in CATALOG[era].items():
            assert cue.era == era
            assert cue.cue_type == cue_type


def test_catalog_passes_every_readability_rule():
    assert validate_catalog() == {}


def test_telegraphs_carry_shape_and_lead_others_do_not():
    for era in ERA_ORDER:
        tele = CATALOG[era]["telegraph"]
        assert tele.shape in TELEGRAPH_SHAPES
        assert tele.lead_ms is not None and tele.lead_ms >= TELEGRAPH_LEAD_BASE_MS
        for cue_type in ("hit_spark", "crit", "death", "pickup"):
            assert CATALOG[era][cue_type].shape is None
            assert CATALOG[era][cue_type].lead_ms is None


def test_crit_reads_bigger_than_hit_spark_in_every_era():
    for era in ERA_ORDER:
        hit, crit = CATALOG[era]["hit_spark"], CATALOG[era]["crit"]
        assert crit.particles > hit.particles
        assert crit.trauma > hit.trauma
        assert crit.duration_ms > hit.duration_ms


def test_pixel_eras_are_frame_locked_and_sprite_budgeted():
    for era in ERA_ORDER:
        if ERAS[era]["max_poly"] != 0:
            continue
        assert frame_budget(era).max_particles == ERAS[era]["max_sprites"]
        for cue in CATALOG[era].values():
            frames = cue.duration_ms / FRAME_MS_60HZ
            assert abs(frames - round(frames)) < 0.05


def test_validate_catalog_flags_missing_era_and_cue():
    partial = {era: dict(cues) for era, cues in CATALOG.items() if era != "8bit"}
    del partial["modern"]["death"]
    problems = validate_catalog(partial)
    assert problems["8bit"] == ["era_missing"]
    assert "death:missing" in problems["modern"]


def test_cue_for_resolves_aliases_and_rejects_unknown_types():
    assert cue_for("nes", "crit") is CATALOG["8bit"]["crit"]
    with pytest.raises(ValueError):
        cue_for("modern", "explosion")


def test_telegraph_lead_floor_scales_with_damage():
    assert min_telegraph_lead_ms(0, 100) == TELEGRAPH_LEAD_BASE_MS
    assert min_telegraph_lead_ms(50, 100) == TELEGRAPH_LEAD_BASE_MS + TELEGRAPH_LEAD_SCALE_MS // 2
    assert min_telegraph_lead_ms(100, 100) == TELEGRAPH_LEAD_BASE_MS + TELEGRAPH_LEAD_SCALE_MS
    assert min_telegraph_lead_ms(500, 100) == min_telegraph_lead_ms(100, 100)
    with pytest.raises(ValueError):
        min_telegraph_lead_ms(10, 0)
    with pytest.raises(ValueError):
        min_telegraph_lead_ms(-1, 100)


def test_telegraph_lead_rule_pass_and_fail():
    assert telegraph_lead_ok(900, 100, 100) is True
    assert telegraph_lead_ok(899, 100, 100) is False
    assert telegraph_lead_ok(250, 0, 100) is True
    assert telegraph_lead_ok(249, 0, 100) is False


def test_telegraph_for_stretches_lead_to_the_floor():
    for era in ERA_ORDER:
        lethal = telegraph_for(era, 120, 100)
        assert telegraph_lead_ok(lethal.lead_ms, 120, 100)
        assert lethal.duration_ms == lethal.lead_ms
        assert duration_ok("telegraph", lethal.duration_ms)
        chip = telegraph_for(era, 1, 100)
        assert chip.lead_ms == CATALOG[era]["telegraph"].lead_ms
    assert telegraph_for("modern", 10, 100, shape="ring").shape == "ring"
    with pytest.raises(ValueError):
        telegraph_for("modern", 10, 100, shape="star")


def test_duration_windows_pass_and_fail():
    for cue_type, (lo, hi) in DURATION_WINDOWS_MS.items():
        assert duration_ok(cue_type, lo)
        assert duration_ok(cue_type, hi)
        assert not duration_ok(cue_type, lo - 1)
        assert not duration_ok(cue_type, hi + 1)
    with pytest.raises(ValueError):
        duration_ok("explosion", 100)


def test_colors_rule_uses_era_color_limit():
    assert colors_ok("8bit", ERAS["8bit"]["colors_max"])
    assert not colors_ok("8bit", ERAS["8bit"]["colors_max"] + 1)
    assert not colors_ok("modern", 0)


def test_validate_cue_reports_each_broken_rule():
    from dataclasses import replace

    bad = replace(CATALOG["8bit"]["telegraph"], duration_ms=10, colors=65, particles=65, shape="star", lead_ms=100)
    assert validate_cue(bad) == [
        "duration_in_window",
        "colors_within_era",
        "particles_within_budget",
        "telegraph_shape_known",
        "telegraph_lead_floor",
    ]
    assert validate_cue(CATALOG["8bit"]["telegraph"]) == []


def test_frame_budget_rule_pass_and_fail():
    budget = frame_budget("8bit")
    spark = CATALOG["8bit"]["hit_spark"]
    assert frame_budget_ok([spark] * budget.max_effects, "8bit")
    assert not frame_budget_ok([spark] * (budget.max_effects + 1), "8bit")
    death = CATALOG["16bit"]["death"]
    heavy = [death] * (frame_budget("16bit").max_particles // death.particles + 1)
    assert not frame_budget_ok(heavy[: frame_budget("16bit").max_effects], "16bit")


def test_plan_frame_keeps_telegraphs_when_over_budget():
    era = "8bit"
    budget = frame_budget(era)
    sparks = [CATALOG[era]["hit_spark"]] * budget.max_effects
    tele = CATALOG[era]["telegraph"]
    plan = plan_frame(sparks + [tele], era)
    assert tele in plan.admitted
    assert len(plan.admitted) == budget.max_effects
    assert len(plan.dropped) == 1 and plan.dropped[0].cue_type == "hit_spark"
    assert frame_budget_ok(plan.admitted, era)


def test_plan_frame_respects_particle_budget():
    era = "16bit"
    death = CATALOG[era]["death"]
    plan = plan_frame([death] * frame_budget(era).max_effects, era)
    assert plan.particles <= frame_budget(era).max_particles
    assert plan.dropped


def test_emit_bridges_into_vfx_state():
    state = VfxState()
    crit = CATALOG["modern"]["crit"]
    burst = emit(state, crit, 1.0, 2.0, 3.0)
    assert burst.count == crit.particles
    assert state.bursts == [burst]
    assert state.trauma == pytest.approx(crit.trauma)
    emit(state, CATALOG["modern"]["pickup"], 0.0, 0.0, 0.0)
    assert state.trauma == pytest.approx(crit.trauma)
