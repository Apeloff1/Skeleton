"""#807 B030: genre template composition."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.genre_template_composition import (
    CompositionError, PackRegistry, compose_slice, verify_slice,
)

PACKS = [
    {"id": "core.movement", "provides": ["movement"], "params": {"speed": 5}},
    {"id": "combat.melee", "provides": ["combat"], "requires": ["movement"], "params": {"dmg": 10}},
    {"id": "quest.objectives", "provides": ["quests"], "requires": ["movement"]},
    {"id": "combat.turn_based", "provides": ["turns"], "conflicts": ["combat.melee"]},
]


def _reg() -> PackRegistry:
    return PackRegistry(PACKS)


def test_compose_action_rpg_slice() -> None:
    s = compose_slice(_reg(), "arpg", ["core.movement", "combat.melee", "quest.objectives"],
                      overrides={"combat.melee": {"dmg": 12}})
    assert s["capabilities"] == {"combat": "combat.melee", "movement": "core.movement",
                                 "quests": "quest.objectives"}
    assert [p["params"] for p in s["packs"] if p["id"] == "combat.melee"] == [{"dmg": 12}]
    assert verify_slice(_reg(), s)


def test_composition_is_order_independent_and_deterministic() -> None:
    a = compose_slice(_reg(), "s", ["core.movement", "combat.melee"])
    b = compose_slice(_reg(), "s", ["combat.melee", "core.movement"])
    assert a == b


def test_same_pack_reused_across_slices_without_fork() -> None:
    reg = _reg()
    a = compose_slice(reg, "a", ["core.movement", "combat.melee"])
    b = compose_slice(reg, "b", ["core.movement", "quest.objectives"])
    da = {p["id"]: p["digest"] for p in a["packs"]}
    db = {p["id"]: p["digest"] for p in b["packs"]}
    assert da["core.movement"] == db["core.movement"]


def test_forking_a_pack_id_is_rejected() -> None:
    with pytest.raises(CompositionError):
        _reg().register({"id": "combat.melee", "provides": ["combat"], "params": {"dmg": 99}})


@pytest.mark.parametrize("ids", [
    ["combat.melee"],
    ["core.movement", "combat.melee", "combat.turn_based"],
    ["core.movement", "core.movement"],
    ["ghost"],
])
def test_invalid_compositions_fail_closed(ids: list[str]) -> None:
    with pytest.raises(CompositionError):
        compose_slice(_reg(), "bad", ids)


def test_undeclared_override_rejected() -> None:
    with pytest.raises(CompositionError):
        compose_slice(_reg(), "s", ["core.movement"], overrides={"core.movement": {"fly": True}})


def test_tampered_slice_fails_verification() -> None:
    s = compose_slice(_reg(), "s", ["core.movement"])
    s["packs"][0]["params"]["speed"] = 99
    assert not verify_slice(_reg(), s)
