from itertools import count

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
    counter = count()
    flaky.register(1, lambda p: {**p, "r": next(counter)})
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

def test_strict_section_custody_rejects_missing_unknown_and_wrong_types():
    section = dict(V1_SECTION)
    for key in ("schema", "world_id", "schema_version", "tick",
                "payload", "canon_digest", "state_digest"):
        omitted = dict(section)
        del omitted[key]
        with pytest.raises(GameplayMigrationError, match="fields invalid"):
            GameplayStateEnvelope.from_section(omitted)
    with pytest.raises(GameplayMigrationError, match="fields invalid"):
        GameplayStateEnvelope.from_section(dict(section, surprise="unreviewed"))
    with pytest.raises(GameplayMigrationError, match="must be a mapping"):
        GameplayStateEnvelope.from_section(None)
    with pytest.raises(GameplayMigrationError, match="invalid tick"):
        GameplayStateEnvelope("w1", 1, True, {}, CANON)
    with pytest.raises(GameplayMigrationError, match="schema_version"):
        GameplayStateEnvelope("w1", True, 0, {}, CANON)


def test_registry_rejects_non_callable_and_invalid_oldest():
    migrations = GameplayMigrations(3)
    with pytest.raises(GameplayMigrationError, match="callable"):
        migrations.register(1, None)
    with pytest.raises(GameplayMigrationError, match="oldest"):
        migrations.missing_steps(0)
    with pytest.raises(GameplayMigrationError, match="oldest"):
        migrations.missing_steps(4)
