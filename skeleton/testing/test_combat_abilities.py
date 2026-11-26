"""B027: deterministic, extensible combat/ability framework."""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest

from skeleton.simulation.game.combat_design import abilities as ab
from skeleton.simulation.game.combat_design.abilities import (
    AbilitySpec,
    CombatError,
    CombatSession,
    Combatant,
    EffectHandler,
    EffectRegistry,
    EffectSpec,
    replay,
)
from skeleton.simulation.game.combat_design.damage import DamageEvent, DamageType, DefenderProfile

ROOT = Path(__file__).resolve().parents[2]

STRIKE = AbilitySpec("strike", damage=DamageEvent(base=100, crit_chance=0.25), cooldown_ticks=2)
IGNITE = AbilitySpec(
    "ignite",
    cost=30,
    cooldown_ticks=5,
    damage=DamageEvent(base=20, dtype=DamageType.FIRE, can_crit=False),
    effects=(EffectSpec("burn", "dot", duration_ticks=4, magnitude=10, dtype=DamageType.FIRE,
                        stacking="stack", max_stacks=3),),
)
BASH = AbilitySpec("bash", damage=DamageEvent(base=5, can_crit=False), effects=(EffectSpec("stun", "stun", 2),))
SUNDER = AbilitySpec("sunder", effects=(EffectSpec("sunder", "armor", 10, magnitude=-500),
                                         EffectSpec("expose", "vulnerability", 10, magnitude=1.2)))
MEND = AbilitySpec("mend", heal=50, target="self", triggers_gcd=False,
                   effects=(EffectSpec("regen", "hot", 4, magnitude=5, period_ticks=2),))
ALL = (STRIKE, IGNITE, BASH, SUNDER, MEND)


def _cast():
    return [
        Combatant("hero", 1000, team="a", level=10, abilities=("strike", "ignite", "bash", "sunder", "mend"),
                  resource_regen=5),
        Combatant("ogre", 2000, team="b", level=10, defense=DefenderProfile(armor=800),
                  abilities=("strike", "bash")),
    ]


SCRIPT = [
    ("cast", "hero", "sunder", "ogre"), ("advance", 1),
    ("cast", "hero", "ignite", "ogre"), ("advance", 1),
    ("cast", "hero", "strike", "ogre"), ("cast", "ogre", "bash", "hero"), ("advance", 1),
    ("cast", "hero", "strike", "ogre"), ("advance", 2),
    ("cast", "hero", "mend", "hero"), ("cast", "ogre", "strike", "hero"), ("advance", 6),
]


def _session(**kw):
    s = CombatSession(seed=7, abilities=ALL, **kw)
    for c in _cast():
        s.add(c)
    return s


def test_replay_is_bit_identical_and_seed_sensitive():
    first = replay(seed=7, abilities=ALL, combatants=_cast, script=SCRIPT)
    second = replay(seed=7, abilities=ALL, combatants=_cast, script=SCRIPT)
    assert first.digest() == second.digest()
    assert first.events == second.events
    other = replay(seed=8, abilities=ALL, combatants=_cast, script=SCRIPT)
    assert other.digest() != first.digest()


def test_cooldown_gcd_and_resource_refusals_change_nothing():
    s = _session(gcd_ticks=1)

    def state():
        return s.state()["combatants"]

    assert s.cast("hero", "ignite", "ogre").ok
    before = state()
    assert s.cast("hero", "strike", "ogre").reason == ab.ON_GLOBAL_COOLDOWN
    assert state() == before
    s.advance(1)
    r = s.cast("hero", "ignite", "ogre")
    assert r.reason == ab.ON_COOLDOWN and "ready_at=5" in r.detail
    hero = s.combatant("hero")
    hero.resource = 0
    s.advance(5)
    before = state()
    assert s.cast("hero", "ignite", "ogre").reason == ab.INSUFFICIENT_RESOURCE
    assert state() == before
    assert hero.resource == 25  # 5 ticks * 5 regen, nothing charged
    assert [e["reason"] for e in s.events if e["kind"] == "cast_refused"] == [
        ab.ON_GLOBAL_COOLDOWN, ab.ON_COOLDOWN, ab.INSUFFICIENT_RESOURCE]


def test_dot_stacks_ticks_and_expires():
    s = _session()
    s.cast("hero", "ignite", "ogre")
    s.advance(1)
    s.combatant("hero").cooldowns.clear()
    s.cast("hero", "ignite", "ogre")
    assert s.combatant("ogre").effects["burn"].stacks == 2

    def dots():
        return [e for e in s.events if e["kind"] == "damage" and e["label"] == "dot:burn"]

    s.advance(4)
    assert len(dots()) == 5  # 1 tick at one stack, then 4 ticks at two stacks
    assert "burn" not in s.combatant("ogre").effects
    assert any(e["kind"] == "effect_expire" and e["effect"] == "burn" for e in s.events)


def test_stun_blocks_casting_until_expiry():
    s = _session()
    s.cast("ogre", "bash", "hero")
    assert s.cast("hero", "strike", "ogre").reason == ab.STUNNED
    s.advance(2)
    assert s.cast("hero", "strike", "ogre").ok


def test_armor_and_vulnerability_effects_raise_damage():
    plain = _session()
    hit_plain = plain.cast("hero", "strike", "ogre").damage
    sundered = _session()
    sundered.cast("hero", "sunder", "ogre")
    profile = sundered.defense_of(sundered.combatant("ogre"))
    assert profile.armor == 300 and profile.vulnerability == pytest.approx(1.2)
    assert sundered.cast("hero", "strike", "ogre").damage > hit_plain


def test_targeting_heal_and_death():
    s = _session()
    assert s.cast("hero", "mend", "ogre").reason == ab.INVALID_TARGET
    assert s.cast("hero", "strike", "hero").reason == ab.INVALID_TARGET
    s.combatant("hero").hp = 900
    assert s.cast("hero", "mend", "hero").heal == 50
    s.combatant("ogre").hp = 1
    r = s.cast("hero", "strike", "ogre")
    assert r.killed and r.damage == 1
    assert s.winner() == "a"
    assert s.cast("ogre", "strike", "hero").reason == ab.ACTOR_DEAD
    assert s.cast("hero", "ignite", "ogre").reason == ab.TARGET_DEAD


def test_custom_effect_kind_is_pluggable():
    class Lifesteal(EffectHandler):
        def on_tick(self, session, holder, effect):
            src = session.combatant(effect.source_id)
            dealt, _ = session._apply_hit(src.combatant_id, holder,
                                          DamageEvent(base=effect.spec.magnitude, dtype=DamageType.TRUE,
                                                      can_crit=False), label="drain")
            session._apply_heal(src.combatant_id, src, dealt, label="drain")

    reg = EffectRegistry()
    reg.register("lifesteal", Lifesteal())
    with pytest.raises(CombatError):
        reg.register("lifesteal", Lifesteal())
    drain = AbilitySpec("drain", effects=(EffectSpec("drain", "lifesteal", 3, magnitude=7),))
    s = CombatSession(seed=1, abilities=(drain,), registry=reg)
    s.add(Combatant("a", 100, team="x", hp=50, abilities=("drain",)))
    s.add(Combatant("b", 100, team="y"))
    s.cast("a", "drain", "b")
    s.advance(3)
    assert s.combatant("b").hp == 79 and s.combatant("a").hp == 71
    with pytest.raises(CombatError):
        CombatSession(seed=1, abilities=(drain,))  # unknown kind fails at registration


def test_spec_validation_fails_closed():
    with pytest.raises(CombatError):
        AbilitySpec("noop")
    with pytest.raises(CombatError):
        EffectSpec("x", "dot", 0)
    with pytest.raises(CombatError):
        EffectSpec("x", "dot", 3, max_stacks=2)
    with pytest.raises(CombatError):
        Combatant("bad id!", 10)
    s = _session()
    assert s.cast("ghost", "strike", "ogre").reason == ab.UNKNOWN_ACTOR
    assert s.cast("ogre", "ignite", "hero").reason == ab.UNKNOWN_ABILITY
    with pytest.raises(CombatError):
        s.add(Combatant("x", 10, abilities=("nope",)))


def test_economy_ability_book_bridge_charges_on_cast_only():
    from skeleton.economy.gameplay.combat import AbilityBook
    from skeleton.economy.gameplay.combat import AbilitySpec as CostSpec
    from skeleton.economy.gameplay.combat_bridge import bind_ability_book
    from skeleton.economy.gameplay.tests.conftest import build_econ

    econ = build_econ(owners=("hero",))
    econ.grant("bounty", "hero", tick=0)  # 100 gold
    book = AbilityBook(econ, [CostSpec("ignite", sink_id="cast")])  # 20 gold per cast
    s = _session()
    receipts = bind_ability_book(s, book)
    for _ in range(5):
        assert s.cast("hero", "ignite", "ogre").ok
        s.combatant("hero").cooldowns.clear()
        s.combatant("hero").resource = 100
    assert econ.balance("hero", "gold") == 0 and len(receipts) == 5
    r = s.cast("hero", "ignite", "ogre")
    assert r.reason == ab.GUARD_REFUSED and "insufficient funds" in r.detail
    assert s.cast("hero", "strike", "ogre").ok  # not in the book: free


def test_ai_tree_mirror_is_byte_identical():
    rel = "game/combat_design/abilities.py"
    assert filecmp.cmp(ROOT / "skeleton/simulation" / rel, ROOT / "skeleton/ai/simulation" / rel, shallow=False)
