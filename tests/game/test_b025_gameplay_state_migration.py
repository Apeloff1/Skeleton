import random

import pytest

from skeleton.game.gameplay.state_migration import (
    GameplayMigrationError, GameplayMigrations, GameplayStateEnvelope,
)

CANON = "c" * 64

# Frozen v1 save fixture: backward compatibility is regression-tested against it.
V1_SECTION = {
    "schema": "skeleton.game.gameplay_state.v1", "world_id": "w1", "schema_version": 1,
    "tick": 42, "payload": {"inv": ["sword"], "hp": 10}, "canon_digest": CANON,
    "parent_save_digest": None,
    "state_digest": "",  # filled below from the canonical digest
}
V1_SECTION["state_digest"] = GameplayStateEnvelope(
    "w1", 1, 42, V1_SECTION["payload"], CANON).state_digest


def _registry():
    r = GameplayMigrations(current_version=3)
    r.register(1, lambda p: {**{k: v for k, v in p.items() if k != "inv"}, "inventory": p["inv"]})
    r.register(2, lambda p: {**p, "hp": {"cur": p["hp"], "max": p["hp"]}})
    return r


def test_v1_fixture_migrates_to_current():
    env, rep = _registry().load_section(V1_SECTION)
    assert env.schema_version == 3 and env.tick == 42
    assert env.payload == {"inventory": ["sword"], "hp": {"cur": 10, "max": 10}}
    assert rep.steps == (1, 2) and rep.source_digest == V1_SECTION["state_digest"]
    assert env.metadata().schema_version == 3


def test_migration_is_deterministic_and_does_not_mutate_source():
    src = GameplayStateEnvelope.from_section(V1_SECTION)
    a, _ = _registry().migrate(src)
    b, _ = _registry().migrate(src)
    assert a.digest == b.digest
    assert src.payload == {"inv": ["sword"], "hp": 10}


def test_current_version_is_noop_and_round_trips():
    env, _ = _registry().load_section(V1_SECTION)
    again, rep = _registry().load_section(env.to_section())
    assert rep.steps == () and again == env


def test_rejects_newer_missing_tampered_and_nondeterministic():
    r = _registry()
    newer = GameplayStateEnvelope("w1", 4, 0, {}, CANON)
    with pytest.raises(GameplayMigrationError, match="newer"):
        r.migrate(newer)
    gap = GameplayMigrations(3)
    gap.register(1, lambda p: p)
    assert gap.missing_steps() == (2,)
    with pytest.raises(GameplayMigrationError, match="missing"):
        gap.load_section(V1_SECTION)
    bad = dict(V1_SECTION, payload={"inv": [], "hp": 999})
    with pytest.raises(GameplayMigrationError, match="digest"):
        r.load_section(bad)
    flaky = GameplayMigrations(2)
    flaky.register(1, lambda p: {**p, "r": random.random()})
    with pytest.raises(GameplayMigrationError, match="non-deterministic"):
        flaky.load_section(V1_SECTION)


def test_registry_validation():
    r = GameplayMigrations(2)
    r.register(1, lambda p: p)
    with pytest.raises(GameplayMigrationError):
        r.register(1, lambda p: p)
    with pytest.raises(GameplayMigrationError):
        r.register(2, lambda p: p)
    with pytest.raises(Exception):
        GameplayStateEnvelope("w1", 1, 0, {"x": float("nan")}, CANON)


def test_section_migrations_match_gf_b_shape():
    steps = _registry().as_section_migrations()
    assert sorted(steps) == [1, 2]
    s = V1_SECTION
    for v in (1, 2):
        s = steps[v](dict(s))
    direct, _ = _registry().load_section(V1_SECTION)
    assert s == direct.to_section()


def test_migration_payload_and_chain_budgets_fail_closed(monkeypatch):
    from skeleton.game.gameplay import state_migration as mod

    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(GameplayMigrationError, match="cyclic"):
        GameplayStateEnvelope("w1", 1, 0, {"cyclic": cyclic}, CANON)
    monkeypatch.setattr(mod, "MAX_PAYLOAD_NODES", 3)
    with pytest.raises(GameplayMigrationError, match="traversal budget"):
        GameplayStateEnvelope("w1", 1, 0, {"items": [1, 2, 3]}, CANON)
    monkeypatch.setattr(mod, "MAX_MIGRATION_STEPS", 1)
    with pytest.raises(GameplayMigrationError, match="step bound"):
        _registry().load_section(V1_SECTION)
    with pytest.raises(GameplayMigrationError, match="callback"):
        GameplayMigrations(2).register(1, None)


def test_migration_callback_output_is_bounded_before_digest():
    huge = GameplayMigrations(2)
    huge.register(1, lambda p: {"payload": [0] * 10_001})
    with pytest.raises(GameplayMigrationError, match="collection exceeds bound"):
        huge.load_section(V1_SECTION)

    def cyclic_result(payload):
        cycle = []
        cycle.append(cycle)
        return {"cycle": cycle}

    cyclic = GameplayMigrations(2)
    cyclic.register(1, cyclic_result)
    with pytest.raises(GameplayMigrationError, match="cyclic"):
        cyclic.load_section(V1_SECTION)


def test_migration_rejects_unbounded_oldest_and_missing_section_fields():
    registry = _registry()
    for oldest in (-10**9, 0, True, 10**9, 4):
        with pytest.raises(GameplayMigrationError):
            registry.missing_steps(oldest)
    assert registry.missing_steps(2) == ()
    for missing in ("world_id", "schema_version", "tick", "payload", "canon_digest"):
        invalid = dict(V1_SECTION)
        invalid.pop(missing)
        with pytest.raises(GameplayMigrationError, match="missing gameplay save field"):
            GameplayStateEnvelope.from_section(invalid)
    with pytest.raises(GameplayMigrationError, match="schema"):
        GameplayStateEnvelope.from_section(None)


@pytest.mark.parametrize("bad", [10**2000, -(10**2000)])
def test_gameplay_save_rejects_oversized_integer_before_digest(bad):
    with pytest.raises(GameplayMigrationError, match="integer exceeds bound"):
        GameplayStateEnvelope("w1", 1, 0, {"value": bad}, CANON)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_gameplay_save_rejects_nonfinite_float_before_copy(bad):
    with pytest.raises(GameplayMigrationError, match="nonfinite"):
        GameplayStateEnvelope("w1", 1, 0, {"value": bad}, CANON)


@pytest.mark.parametrize("tick", [True, -1, 2**63, 10**1000, 1.5, "42"])
def test_gameplay_save_rejects_unbounded_tick_and_unrecognized_fields(tick):
    with pytest.raises(GameplayMigrationError, match="bounded tick"):
        GameplayStateEnvelope("w1", 1, tick, {"hp": 10}, CANON)


def test_gameplay_section_rejects_unknown_fields_before_migration():
    tampered = dict(V1_SECTION, unexpected={"future": "untrusted"})
    with pytest.raises(GameplayMigrationError, match="unknown gameplay save field"):
        GameplayStateEnvelope.from_section(tampered)
    missing = dict(V1_SECTION)
    missing.pop("parent_save_digest")
    with pytest.raises(GameplayMigrationError, match="missing gameplay save field"):
        GameplayStateEnvelope.from_section(missing)
    assert GameplayStateEnvelope.from_section(V1_SECTION).tick == 42


def test_migration_invalid_first_result_does_not_invoke_callback_twice():
    calls = []

    def invalid_first(payload):
        calls.append(1)
        return {"too_many": [0] * 10_001}

    registry = GameplayMigrations(2)
    registry.register(1, invalid_first)
    with pytest.raises(GameplayMigrationError, match="collection exceeds bound"):
        registry.load_section(V1_SECTION)
    assert calls == [1]


def test_gameplay_save_rejects_hostile_mapping_hooks_before_iteration():
    """A signed-looking save must not execute arbitrary Mapping methods."""
    class HostileDict(dict):
        def __iter__(self):
            raise AssertionError("hostile mapping iteration executed")

    with pytest.raises(GameplayMigrationError, match="plain dict"):
        GameplayStateEnvelope.from_section(HostileDict(V1_SECTION))
    with pytest.raises(GameplayMigrationError, match="plain dict"):
        GameplayStateEnvelope.from_section(dict(V1_SECTION, payload=HostileDict({"hp": 10})))

    many_fields = dict(V1_SECTION)
    many_fields.update({f"unknown_{i}": i for i in range(1000)})
    with pytest.raises(GameplayMigrationError, match="unknown gameplay save field"):
        GameplayStateEnvelope.from_section(many_fields)
