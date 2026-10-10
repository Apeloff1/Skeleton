"""Combat design layer: damage, telegraph readability, difficulty curves, encounter sim."""

from __future__ import annotations

import json

import pytest

from skeleton.simulation.game.combat_design import (
    CASUAL,
    CORE,
    EXPERT,
    MAX_ARMOR_DR,
    MAX_RESIST,
    TIER_SCALING,
    TTK_TARGETS_S,
    Archetype,
    AttackTelegraph,
    BUDGET_COST,
    DamageEvent,
    DamageType,
    DefenderProfile,
    DifficultyTier,
    PatternEntry,
    TelegraphChannel as Ch,
    ThreatTier,
    archetype_hp,
    armor_damage_reduction,
    audit_pattern,
    audit_telegraph,
    balance_table,
    build_zone_curve,
    clear_rate,
    compose_encounter,
    effective_health,
    encounter_budget,
    expected_damage,
    is_readable,
    resolve_damage,
    simulate_encounter,
    time_to_kill_s,
    validate_curve,
)

TIERS = (DifficultyTier.STORY, DifficultyTier.NORMAL, DifficultyTier.HEROIC, DifficultyTier.MYTHIC)


def _cleave() -> AttackTelegraph:
    return AttackTelegraph("cleave", ThreatTier.MINOR, 600, 300, 400, frozenset({Ch.BODY_ANIM, Ch.VFX_GLOW}), 0.10)


def _slam() -> AttackTelegraph:
    return AttackTelegraph(
        "ground_slam", ThreatTier.MAJOR, 1000, 400, 400, frozenset({Ch.BODY_ANIM, Ch.GROUND_DECAL}), 0.35, escape_distance_m=3.0
    )


def _annihilate() -> AttackTelegraph:
    return AttackTelegraph(
        "annihilate",
        ThreatTier.LETHAL,
        1600,
        500,
        900,
        frozenset({Ch.BODY_ANIM, Ch.GROUND_DECAL, Ch.AUDIO, Ch.UI_CAST_BAR}),
        1.0,
        escape_distance_m=5.0,
    )


def _rotation():
    return [_cleave(), _slam(), _cleave(), _annihilate()]


def _boss_kwargs(**over):
    kw = dict(enemy_hp=60_000.0, rotation=_rotation(), player_max_hp=1000.0, player_dps=1000.0, profile=CORE)
    kw.update(over)
    return kw


# --- damage -----------------------------------------------------------------


def test_armor_dr_monotone_and_capped():
    prev = -1.0
    for armor in (0, 100, 500, 2000, 10_000, 100_000):
        dr = armor_damage_reduction(armor, 10)
        assert dr >= prev
        assert 0.0 <= dr <= MAX_ARMOR_DR
        prev = dr
    assert armor_damage_reduction(100_000, 1) == MAX_ARMOR_DR
    # Higher-level attackers punch through the same armor.
    assert armor_damage_reduction(2000, 60) < armor_damage_reduction(2000, 10)


def test_true_damage_ignores_all_mitigation():
    tank = DefenderProfile(armor=50_000, flat_reduction=40, vulnerability=1.5)
    hit = resolve_damage(DamageEvent(100, DamageType.TRUE), tank, crit_roll=0.9)
    assert hit.final == 100
    assert hit.mitigation_fraction == 0.0


def test_resist_is_capped():
    d = DefenderProfile(resistances={DamageType.FIRE: 1.0})
    hit = resolve_damage(DamageEvent(1000, DamageType.FIRE), d, crit_roll=0.9)
    assert hit.mitigation_fraction == MAX_RESIST
    assert hit.final == 250


def test_crit_and_variance_band():
    e = DamageEvent(1000, crit_chance=0.25, crit_mult=2.0)
    d = DefenderProfile()
    assert resolve_damage(e, d, crit_roll=0.1).final == 2000
    assert resolve_damage(e, d, crit_roll=0.5).final == 1000
    lo = resolve_damage(e, d, crit_roll=0.5, variance_roll=0.0).final
    hi = resolve_damage(e, d, crit_roll=0.5, variance_roll=0.999999).final
    assert 950 <= lo <= hi <= 1050


def test_resolve_is_deterministic():
    e = DamageEvent(777, DamageType.SHADOW, attacker_level=30, crit_chance=0.3)
    d = DefenderProfile(armor=900, resistances={DamageType.SHADOW: 0.2}, flat_reduction=5)
    a = resolve_damage(e, d, crit_roll=0.21, variance_roll=0.33).as_dict()
    b = resolve_damage(e, d, crit_roll=0.21, variance_roll=0.33).as_dict()
    assert a == b


def test_expected_damage_matches_crit_grid_mean():
    e = DamageEvent(500, DamageType.PHYSICAL, attacker_level=20, crit_chance=0.2, crit_mult=2.5)
    d = DefenderProfile(armor=1500, flat_reduction=10, vulnerability=1.1)
    n = 1000
    mean = sum(resolve_damage(e, d, crit_roll=i / n).final for i in range(n)) / n
    assert abs(mean - expected_damage(e, d)) <= 1.0


def test_effective_health_grows_with_armor():
    assert effective_health(1000, DefenderProfile(), DamageType.PHYSICAL) == pytest.approx(1000)
    assert effective_health(1000, DefenderProfile(armor=3000), DamageType.PHYSICAL, 10) > 1500


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DamageEvent(-1),
        lambda: DamageEvent(10, attacker_level=0),
        lambda: DamageEvent(10, crit_chance=1.5),
        lambda: DamageEvent(10, crit_mult=0.5),
        lambda: DefenderProfile(armor=-5),
        lambda: DefenderProfile(vulnerability=3.0),
        lambda: DefenderProfile(resistances={DamageType.PHYSICAL: 0.5}),
        lambda: resolve_damage(DamageEvent(10), DefenderProfile(), crit_roll=1.0),
    ],
)
def test_damage_fails_closed(factory):
    with pytest.raises(ValueError):
        factory()


# --- telegraphs ------------------------------------------------------------


def test_reference_rotation_is_readable():
    for t in _rotation():
        assert audit_telegraph(t) == [], t.name
    pattern = [PatternEntry(0, _cleave()), PatternEntry(2500, _slam()), PatternEntry(6000, _annihilate()), PatternEntry(9000, _cleave())]
    assert audit_pattern(pattern) == []
    assert is_readable(pattern)


def _codes(t: AttackTelegraph):
    return {v.code for v in audit_telegraph(t)}


def test_each_readability_rule_fires():
    base = _annihilate()
    assert "windup_below_tier_floor" in _codes(base.__class__(**{**base.__dict__, "windup_ms": 900, "recovery_ms": 900}))
    assert "lethal_without_audio" in _codes(base.__class__(**{**base.__dict__, "channels": frozenset({Ch.BODY_ANIM, Ch.GROUND_DECAL})}))
    assert "no_punish_window" in _codes(base.__class__(**{**base.__dict__, "recovery_ms": 200}))
    assert "unescapable" in _codes(base.__class__(**{**base.__dict__, "escape_distance_m": 12.0}))
    assert "active_too_long" in _codes(base.__class__(**{**base.__dict__, "active_ms": 2500}))
    minor = _cleave()
    assert "damage_exceeds_tier" in _codes(minor.__class__(**{**minor.__dict__, "damage_fraction": 0.4}))
    slam = _slam()
    assert "too_few_channels" in _codes(slam.__class__(**{**slam.__dict__, "channels": frozenset({Ch.BODY_ANIM})}))


def test_pattern_rules():
    overlap = [PatternEntry(0, _slam()), PatternEntry(500, _annihilate())]
    assert "overlapping_major_windups" in {v.code for v in audit_pattern(overlap)}
    lethal = _annihilate()
    resolve = lethal.windup_ms + lethal.active_ms
    crowded = [PatternEntry(0, lethal), PatternEntry(resolve + 100, _cleave())]
    assert "no_breather_after_lethal" in {v.code for v in audit_pattern(crowded)}
    roomy = [PatternEntry(0, lethal), PatternEntry(resolve + 400, _cleave())]
    assert audit_pattern(roomy) == []


def test_scaling_respects_floor_but_never_hides_violations():
    fast = _slam().scaled(0.25, 1.0)
    assert fast.windup_ms == 600  # clamped to MAJOR floor
    cheap = AttackTelegraph("cheap_shot", ThreatTier.LETHAL, 300, 200, 200, frozenset({Ch.BODY_ANIM}), 1.0, 4.0)
    assert cheap.scaled(1.0, 1.0).windup_ms == 300
    assert not is_readable(cheap.scaled(1.0, 1.0))


# --- difficulty ------------------------------------------------------------


def test_tier_scaling_is_monotone():
    for easier, harder in zip(TIERS, TIERS[1:]):
        a, b = TIER_SCALING[easier], TIER_SCALING[harder]
        assert a.enemy_hp_mult < b.enemy_hp_mult
        assert a.enemy_damage_mult < b.enemy_damage_mult
        assert a.windup_scale > b.windup_scale


@pytest.mark.parametrize("archetype", list(Archetype))
def test_ttk_bands_hold_for_core_normal_and_casual_story(archetype):
    lo, hi = TTK_TARGETS_S[archetype]
    dps = 1234.0
    core_ttk = time_to_kill_s(archetype_hp(archetype, dps), dps * CORE.dps_efficiency)
    assert lo <= core_ttk <= hi
    casual_ttk = time_to_kill_s(archetype_hp(archetype, dps, DifficultyTier.STORY), dps * CASUAL.dps_efficiency)
    assert lo <= casual_ttk <= hi


def test_zone_curve_is_healthy():
    # Realistic zone lengths; very short zones cannot ramp 0.2 -> 1.0 without a spike.
    for n in (10, 16, 25):
        curve = build_zone_curve(n)
        assert validate_curve(curve) == [], (n, curve)
        assert curve[-1] == max(curve)
    assert "spike" in validate_curve(build_zone_curve(2))


def test_bad_curves_are_flagged():
    assert set(validate_curve([0.5] * 5)) >= {"final_not_peak", "non_positive_trend"}
    assert "spike" in validate_curve([0.2, 0.3, 0.9, 0.4, 1.0])
    assert "no_breather" in validate_curve([0.1 * (i + 1) for i in range(10)])
    assert validate_curve([1.0]) == ["too_short"]


def test_encounter_composition_fits_budget():
    for intensity in build_zone_curve(10):
        budget = encounter_budget(intensity)
        comp = compose_encounter(budget, intensity)
        assert sum(BUDGET_COST[a] * n for a, n in comp.items()) <= budget
        assert comp[Archetype.BOSS] <= 1
    peak = compose_encounter(encounter_budget(1.0), 1.0)
    assert peak[Archetype.BOSS] == 1
    assert compose_encounter(encounter_budget(0.2), 0.2)[Archetype.ELITE] == 0
    assert encounter_budget(0.5, party_size=5) > encounter_budget(0.5)


# --- encounter sim ---------------------------------------------------------


def test_sim_is_deterministic():
    a = simulate_encounter(seed=7, **_boss_kwargs())
    b = simulate_encounter(seed=7, **_boss_kwargs())
    assert a == b
    assert simulate_encounter(seed=8, **_boss_kwargs(profile=CASUAL)).digest != a.digest


def test_expert_never_gets_hit_by_readable_normal_rotation():
    for seed in range(20):
        out = simulate_encounter(seed=seed, **_boss_kwargs(profile=EXPERT))
        assert out.cleared, out
        assert out.hits_taken == 0


def test_unreadable_lethal_cannot_be_beaten():
    cheap = AttackTelegraph("cheap_shot", ThreatTier.LETHAL, 300, 200, 200, frozenset({Ch.BODY_ANIM}), 1.0, 4.0)
    assert not is_readable(cheap)
    for profile in (CASUAL, CORE, EXPERT):
        assert clear_rate(10, **_boss_kwargs(rotation=[cheap], profile=profile)) == 0.0


def test_clear_rate_monotone_in_skill_and_tier():
    for tier in TIERS:
        rates = [clear_rate(25, **_boss_kwargs(profile=p, tier=tier)) for p in (CASUAL, CORE, EXPERT)]
        assert rates == sorted(rates), (tier, rates)
    for profile in (CASUAL, CORE, EXPERT):
        rates = [clear_rate(25, **_boss_kwargs(profile=profile, tier=t)) for t in TIERS]
        assert rates == sorted(rates, reverse=True), (profile, rates)


def test_story_is_clearable_by_casual_players():
    assert clear_rate(20, **_boss_kwargs(profile=CASUAL, tier=DifficultyTier.STORY)) >= 0.9


def test_sim_fails_closed():
    with pytest.raises(ValueError):
        simulate_encounter(**_boss_kwargs(rotation=[]))
    with pytest.raises(ValueError):
        simulate_encounter(**_boss_kwargs(enemy_hp=0))
    with pytest.raises(ValueError):
        clear_rate(5, seed=1, **_boss_kwargs())


def test_balance_table_is_json_and_complete():
    table = balance_table()
    text = json.dumps(table, sort_keys=True)
    assert json.loads(text) == table
    assert set(table) >= {"damage", "telegraph", "difficulty", "ttk_targets_s", "budget_cost", "skill_profiles", "sim"}
    assert table["telegraph"]["tiers"]["lethal"]["max_damage_fraction"] is None


def test_deadline_never_resolves_future_attack_or_clear():
    result = simulate_encounter(**_boss_kwargs(enemy_hp=1e8, max_time_ms=100))
    assert result.reason == "timeout"
    assert result.time_ms == 100
    assert result.attacks == result.hits_taken == result.dodges == 0
    assert result.player_hp_fraction == 1.0
    # The previous full-cycle accounting claimed a kill after this deadline.
    result = simulate_encounter(**_boss_kwargs(enemy_hp=1000, max_time_ms=100))
    assert not result.cleared
    assert result.time_ms == 100


def test_continuous_damage_clear_time_is_exact_in_windup_and_recovery():
    early = simulate_encounter(**_boss_kwargs(enemy_hp=80, max_time_ms=100))
    assert early.cleared and early.time_ms == 100 and early.attacks == 0
    recovery = simulate_encounter(**_boss_kwargs(enemy_hp=800, rotation=[_cleave()]))
    assert recovery.cleared and recovery.time_ms == 1000
    assert recovery.attacks == 1
    assert recovery.attacks == recovery.hits_taken + recovery.dodges


@pytest.mark.parametrize("field,value", [
    ("player_dps", float("nan")), ("player_max_hp", float("inf")),
    ("enemy_hp", True), ("move_speed_mps", float("inf")),
    ("max_time_ms", True), ("max_time_ms", 100.5), ("seed", True),
])
def test_simulation_rejects_unbounded_or_ambiguous_input(field, value):
    with pytest.raises(ValueError):
        simulate_encounter(**_boss_kwargs(**{field: value}))


def test_outcome_identity_binds_all_design_and_profile_inputs():
    from skeleton.simulation.game.combat_design import SkillProfile
    a = simulate_encounter(**_boss_kwargs(enemy_hp=80, max_time_ms=500))
    b = simulate_encounter(**_boss_kwargs(enemy_hp=80, max_time_ms=501))
    assert a.time_ms == b.time_ms == 100
    assert a.digest != b.digest
    alternate = SkillProfile(CORE.name, CORE.reaction_mean_ms + 1, CORE.reaction_sd_ms, CORE.dps_efficiency)
    c = simulate_encounter(**_boss_kwargs(enemy_hp=80, max_time_ms=500, profile=alternate))
    assert a.digest != c.digest  # same name isn't the same profile


def test_design_matrix_is_reproducible_and_reconciles_every_trial():
    from skeleton.simulation.game.combat_design import evaluate_encounter_design
    args = dict(enemy_hp=1000, rotation=_rotation(), player_max_hp=1000, player_dps=1000, n_seeds=4, max_time_ms=5000)
    a = evaluate_encounter_design(**args)
    assert a == evaluate_encounter_design(**args)
    assert len(a["rows"]) == 12
    assert len(a["digest"]) == 64
    assert a["human_playtesting"] is False and a["auto_apply"] is False
    for row in a["rows"]:
        assert row["clears"] + row["deaths"] + row["timeouts"] == 4
        assert len(row["outcome_digests"]) == 4
        assert row["p95_clear_ms"] is None or row["p95_clear_ms"] <= 5000
    # Harder tiers can exceed a damage tier's authored ceiling even when
    # simulations clear. Report must not confuse survivability with fairness.
    assert any(row["readability_violations"] for row in a["rows"])


def test_balance_cli_consumes_real_file_and_rejects_ambiguous_json(tmp_path, capsys):
    from scripts.balance_combat_encounter import main
    config = {
        "schema": "combat.encounter_input.v1", "enemy_hp": 1000,
        "player_max_hp": 1000, "player_dps": 1000,
        "rotation": [{"name": "cleave", "tier": "minor", "windup_ms": 600,
                      "active_ms": 300, "recovery_ms": 400,
                      "channels": ["body_anim", "vfx_glow"], "damage_fraction": 0.1}],
    }
    source = tmp_path / "encounter.json"
    source.write_text(json.dumps(config))
    assert main(["--input", str(source), "--seeds", "2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "combat.design_report.v1"
    assert len(report["rows"]) == 12
    assert report["inputs"]["rotation"][0]["name"] == "cleave"
    source.write_text('{"schema":"combat.encounter_input.v1","schema":"forged"}')
    assert main(["--input", str(source)]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "combat_design_input_rejected"


@pytest.mark.parametrize("field,value", [("n_seeds", 129), ("n_seeds", True), ("max_time_ms", 300001)])
def test_design_report_work_budget_is_enforced(field, value):
    from skeleton.simulation.game.combat_design import evaluate_encounter_design
    args = dict(enemy_hp=1000, rotation=_rotation(), player_max_hp=1000, player_dps=1000)
    with pytest.raises(ValueError):
        evaluate_encounter_design(**args, **{field: value})
