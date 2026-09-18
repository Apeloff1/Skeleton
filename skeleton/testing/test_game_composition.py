"""Fail-closed regressions for the gameplay composition contract (#943)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from skeleton.game import (
    AIBehaviorSpec,
    CANONICAL_KIND_ORDER,
    COMPOSITION_CONTRACT_VERSION,
    CombatStyle,
    CombatSystemSpec,
    CompositionEvent,
    CompositionEventKind,
    EconomySystemSpec,
    GameCompositionError,
    GameMechanicsGenerator,
    GameplayComposer,
    MECHANICS_SURFACE_VERSION,
    MechanicComponent,
    MechanicComponentRef,
    MechanicType,
    ProgressionStyle,
    ProgressionSystemSpec,
    apply_composition_events,
    compose_gameplay,
)
from skeleton.game.mechanics import GameMechanicsError

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_SOURCE = (REPO_ROOT / "skeleton/game/composition.py").read_text(encoding="utf-8")
MECHANICS_SOURCE = (REPO_ROOT / "skeleton/game/mechanics.py").read_text(encoding="utf-8")


def _ref(component_id: str, kind: MechanicType) -> MechanicComponentRef:
    return MechanicComponentRef(component_id=component_id, kind=kind)


def _progression(**overrides: object) -> MechanicComponent:
    values = {
        "style": ProgressionStyle.LINEAR,
        "max_level": 5,
        "include_prestige": False,
        "skill_tree_branches": 1,
    }
    values.update(overrides)
    return MechanicComponent(
        ref=_ref("progression_core", MechanicType.PROGRESSION),
        spec=ProgressionSystemSpec(**values),
    )


def _economy(**overrides: object) -> MechanicComponent:
    values = {
        "currencies": ("gold", "gems"),
        "include_trading": True,
        "include_crafting": False,
        "inflation_model": False,
    }
    values.update(overrides)
    return MechanicComponent(
        ref=_ref("economy_core", MechanicType.ECONOMY),
        spec=EconomySystemSpec(**values),
    )


def _combat(**overrides: object) -> MechanicComponent:
    values = {
        "style": CombatStyle.TURN_BASED,
        "include_magic": True,
        "include_status_effects": True,
        "party_based": False,
        "enemy_ai_complexity": "moderate",
    }
    values.update(overrides)
    return MechanicComponent(
        ref=_ref("combat_core", MechanicType.COMBAT),
        spec=CombatSystemSpec(**values),
    )


def _ai(component_id: str = "ai_guard", entity_type: str = "guard", **overrides: object) -> MechanicComponent:
    values = {
        "entity_type": entity_type,
        "behaviors": ("raise_alarm",),
        "aggression_level": 0.5,
        "intelligence_level": 0.5,
    }
    values.update(overrides)
    return MechanicComponent(
        ref=_ref(component_id, MechanicType.AI_BEHAVIOR),
        spec=AIBehaviorSpec(**values),
    )


def _full_set() -> tuple[MechanicComponent, ...]:
    return (_ai(), _combat(), _economy(), _progression())


def _codes(exc: GameCompositionError) -> tuple[str, ...]:
    return tuple(exc.context["codes"])


def test_composition_order_is_canonical_kind_then_component_id() -> None:
    later_ai = _ai("ai_sentry", "sentry")
    composed = compose_gameplay((later_ai, _combat(), _ai(), _economy(), _progression()))

    assert tuple(item.kind for item in composed.order) == (
        MechanicType.PROGRESSION,
        MechanicType.ECONOMY,
        MechanicType.COMBAT,
        MechanicType.AI_BEHAVIOR,
        MechanicType.AI_BEHAVIOR,
    )
    assert tuple(item.component_id for item in composed.order) == (
        "progression_core",
        "economy_core",
        "combat_core",
        "ai_guard",
        "ai_sentry",
    )
    assert tuple(CANONICAL_KIND_ORDER) == (
        MechanicType.PROGRESSION,
        MechanicType.ECONOMY,
        MechanicType.COMBAT,
        MechanicType.AI_BEHAVIOR,
    )


def test_explicit_dependencies_override_kind_order() -> None:
    economy = MechanicComponent(
        ref=_ref("economy_core", MechanicType.ECONOMY),
        spec=EconomySystemSpec(currencies=("gold",)),
        depends_on=("combat_core",),
    )
    composed = compose_gameplay((_progression(), economy, _combat()))

    assert tuple(item.component_id for item in composed.order) == (
        "progression_core",
        "combat_core",
        "economy_core",
    )
    assert composed.components[2].depends_on == ("combat_core",)


def test_input_shuffle_does_not_change_fingerprint_or_order() -> None:
    components = _full_set()
    first = compose_gameplay(components)
    second = compose_gameplay(tuple(reversed(components)))

    assert first.fingerprint == second.fingerprint
    assert first.replay_evidence.to_dict() == second.replay_evidence.to_dict()
    assert tuple(item.component_id for item in first.order) == tuple(
        item.component_id for item in second.order
    )


def test_conflicting_prestige_without_flag_is_rejected() -> None:
    prestige = MechanicComponent(
        ref=_ref("progression_core", MechanicType.PROGRESSION),
        spec=ProgressionSystemSpec(
            style=ProgressionStyle.PRESTIGE,
            max_level=5,
            include_prestige=False,
            skill_tree_branches=0,
        ),
    )
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((prestige,))
    assert "conflict_prestige" in _codes(raised.value)
    assert raised.value.context["diagnostics"][0]["component_ids"] == ["progression_core"]


def test_conflicting_skill_tree_without_branches_is_rejected() -> None:
    skill_tree = MechanicComponent(
        ref=_ref("progression_core", MechanicType.PROGRESSION),
        spec=ProgressionSystemSpec(
            style=ProgressionStyle.SKILL_TREE,
            max_level=5,
            skill_tree_branches=0,
        ),
    )
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((skill_tree,))
    assert "conflict_skill_tree" in _codes(raised.value)


def test_party_combat_without_progression_is_rejected() -> None:
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((_combat(party_based=True),))
    assert "conflict_party_progression" in _codes(raised.value)


def test_crafting_economy_without_skill_tree_is_rejected() -> None:
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((_economy(include_crafting=True), _progression(skill_tree_branches=0)))
    assert "conflict_crafting_progression" in _codes(raised.value)


def test_card_based_party_combat_is_rejected() -> None:
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((_progression(), _combat(style=CombatStyle.CARD_BASED, party_based=True)))
    assert "conflict_card_party" in _codes(raised.value)


def test_duplicate_combat_components_are_rejected() -> None:
    second = MechanicComponent(
        ref=_ref("combat_alt", MechanicType.COMBAT),
        spec=CombatSystemSpec(style=CombatStyle.REAL_TIME),
    )
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((_combat(), second))
    assert "duplicate_kind" in _codes(raised.value)


def test_duplicate_ai_entity_types_are_rejected() -> None:
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((_ai("ai_one", "guard"), _ai("ai_two", "guard")))
    assert "duplicate_entity_type" in _codes(raised.value)


def test_invalid_dependency_reference_is_rejected() -> None:
    combat = MechanicComponent(
        ref=_ref("combat_core", MechanicType.COMBAT),
        spec=CombatSystemSpec(style=CombatStyle.TURN_BASED),
        depends_on=("missing_progress",),
    )
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((combat, _progression()))
    assert "invalid_dependency" in _codes(raised.value)
    assert "missing_progress" in raised.value.context["diagnostics"][0]["component_ids"]


def test_self_dependency_is_rejected() -> None:
    combat = MechanicComponent(
        ref=_ref("combat_core", MechanicType.COMBAT),
        spec=CombatSystemSpec(style=CombatStyle.TURN_BASED),
        depends_on=("combat_core",),
    )
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((combat,))
    assert "self_dependency" in _codes(raised.value)


def test_dependency_cycle_is_rejected() -> None:
    combat = MechanicComponent(
        ref=_ref("combat_core", MechanicType.COMBAT),
        spec=CombatSystemSpec(style=CombatStyle.TURN_BASED),
        depends_on=("economy_core",),
    )
    economy = MechanicComponent(
        ref=_ref("economy_core", MechanicType.ECONOMY),
        spec=EconomySystemSpec(currencies=("gold",)),
        depends_on=("combat_core",),
    )
    with pytest.raises(GameCompositionError) as raised:
        compose_gameplay((combat, economy))
    assert "dependency_cycle" in _codes(raised.value)


def test_kind_spec_mismatch_is_rejected() -> None:
    with pytest.raises(GameCompositionError) as raised:
        MechanicComponent(
            ref=_ref("combat_core", MechanicType.COMBAT),
            spec=EconomySystemSpec(currencies=("gold",)),
        )
    assert raised.value.context["reason"] == "kind_spec_mismatch"


def test_unsupported_kind_and_version_are_rejected() -> None:
    with pytest.raises(GameCompositionError) as raised_kind:
        MechanicComponentRef(component_id="physics_core", kind=MechanicType.PHYSICS)
    assert raised_kind.value.context["reason"] == "unsupported_kind"

    with pytest.raises(GameCompositionError) as raised_version:
        MechanicComponentRef(
            component_id="combat_core",
            kind=MechanicType.COMBAT,
            version="game.mechanics.v0",
        )
    assert raised_version.value.context["reason"] == "unsupported_version"

    with pytest.raises(GameCompositionError) as raised_id:
        MechanicComponentRef(component_id="Combat-Core", kind=MechanicType.COMBAT)
    assert raised_id.value.context["reason"] == "invalid_identifier"


def test_empty_and_unknown_contract_versions_fail_closed() -> None:
    with pytest.raises(GameCompositionError) as empty:
        compose_gameplay(())
    assert "empty_composition" in _codes(empty.value)

    with pytest.raises(GameCompositionError) as version:
        compose_gameplay(_full_set(), contract_version="game.composition.v0")
    assert version.value.context["reason"] == "unsupported_contract_version"


def test_composed_systems_consume_mechanics_generator_with_deterministic_ids() -> None:
    composed = compose_gameplay(_full_set())
    combat = composed.system_for(MechanicType.COMBAT)
    generated = GameMechanicsGenerator.generate_combat_system(
        CombatSystemSpec(style=CombatStyle.TURN_BASED)
    )

    assert combat is not None
    assert combat["id"] == "combat:combat_core"
    assert combat["component_id"] == "combat_core"
    assert combat["contract_version"] == MECHANICS_SURFACE_VERSION
    assert combat["core_mechanics"] == generated["core_mechanics"]
    assert combat["style"] == "turn_based"
    assert "uuid" not in combat["id"]

    first = compose_gameplay(_full_set())
    second = compose_gameplay(_full_set())
    assert first.fingerprint == second.fingerprint
    assert first.components[2].system["id"] == second.components[2].system["id"]


def test_real_time_composition_keeps_mechanics_template() -> None:
    composed = compose_gameplay((_combat(style=CombatStyle.REAL_TIME),))
    combat = composed.system_for(MechanicType.COMBAT)
    assert combat is not None
    assert combat["core_mechanics"]["structure"] == "continuous"
    assert combat["core_mechanics"]["cooldown_based"] is True


def test_state_transitions_are_deterministic_and_ordered() -> None:
    composed = compose_gameplay(_full_set())
    events = (
        CompositionEvent(CompositionEventKind.AWARD_XP, {"amount": 100}),
        CompositionEvent(CompositionEventKind.CREDIT, {"currency": "gold", "amount": 25}),
        CompositionEvent(CompositionEventKind.SPEND, {"currency": "gold", "amount": 10}),
        CompositionEvent(
            CompositionEventKind.AI_TRANSITION,
            {"entity_type": "guard", "to_state": "alert"},
        ),
    )
    first_state, first_evidence = apply_composition_events(composed, events)
    second_state, second_evidence = apply_composition_events(composed, events)

    assert first_state.fingerprint == second_state.fingerprint
    assert first_evidence.to_dict() == second_evidence.to_dict()
    assert first_state.tick == 4
    assert first_state.xp == 100
    assert first_state.level == 2
    assert first_state.currency_balances["gold"] == 15
    assert first_state.ai_states["guard"] == "alert"
    assert first_evidence.transition_count == 4
    assert first_evidence.component_order == (
        "progression_core",
        "economy_core",
        "combat_core",
        "ai_guard",
    )
    assert first_evidence.contract_version == COMPOSITION_CONTRACT_VERSION
    assert first_evidence.mechanics_version == MECHANICS_SURFACE_VERSION
    assert first_evidence.composition_fingerprint == composed.fingerprint


def test_invalid_transitions_and_references_fail_closed_without_partial_mutation() -> None:
    composed = compose_gameplay(_full_set())
    original = GameplayComposer.initial_state(composed)

    with pytest.raises(GameCompositionError) as spend:
        GameplayComposer.apply_event(
            composed,
            original,
            CompositionEvent(CompositionEventKind.SPEND, {"currency": "gold", "amount": 1}),
        )
    assert spend.value.context["reason"] == "insufficient_funds"

    with pytest.raises(GameCompositionError) as currency:
        GameplayComposer.apply_event(
            composed,
            original,
            CompositionEvent(CompositionEventKind.CREDIT, {"currency": "platinum", "amount": 1}),
        )
    assert currency.value.context["reason"] == "unknown_currency"

    with pytest.raises(GameCompositionError) as transition:
        GameplayComposer.apply_event(
            composed,
            original,
            CompositionEvent(
                CompositionEventKind.AI_TRANSITION,
                {"entity_type": "guard", "to_state": "attack"},
            ),
        )
    assert transition.value.context["reason"] == "invalid_transition"

    with pytest.raises(GameCompositionError) as entity:
        GameplayComposer.apply_event(
            composed,
            original,
            CompositionEvent(
                CompositionEventKind.AI_TRANSITION,
                {"entity_type": "dragon", "to_state": "alert"},
            ),
        )
    assert entity.value.context["reason"] == "unknown_entity"

    assert original.fingerprint == GameplayComposer.initial_state(composed).fingerprint
    assert original.currency_balances["gold"] == 0
    assert original.ai_states["guard"] == "idle"


def test_replay_evidence_is_stable_and_versioned() -> None:
    composed = compose_gameplay(_full_set())
    evidence = composed.replay_evidence.to_dict()

    assert evidence["contract_version"] == "game.composition.v1"
    assert evidence["mechanics_version"] == "game.mechanics.v1"
    assert evidence["component_order"] == [
        "progression_core",
        "economy_core",
        "combat_core",
        "ai_guard",
    ]
    assert evidence["component_versions"] == [
        ["progression_core", MECHANICS_SURFACE_VERSION],
        ["economy_core", MECHANICS_SURFACE_VERSION],
        ["combat_core", MECHANICS_SURFACE_VERSION],
        ["ai_guard", MECHANICS_SURFACE_VERSION],
    ]
    assert evidence["kind_order"] == ["progression", "economy", "combat", "ai_behavior"]
    assert evidence["transition_count"] == 0
    assert len(evidence["composition_fingerprint"]) == 64

    events = (CompositionEvent(CompositionEventKind.AWARD_XP, {"amount": 50}),)
    _, first = apply_composition_events(composed, events)
    _, second = apply_composition_events(composed, events)
    assert first.to_dict() == second.to_dict()
    assert first.transition_fingerprints == second.transition_fingerprints
    assert first.state_fingerprint == second.state_fingerprint


def test_composition_module_stays_local_and_does_not_rewrite_mechanics() -> None:
    tree = ast.parse(COMPOSITION_SOURCE)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])

    imported.discard("__future__")
    assert imported <= {
        "copy",
        "hashlib",
        "json",
        "re",
        "collections",
        "dataclasses",
        "enum",
        "types",
        "typing",
        "skeleton",
    }
    assert "socket" not in imported
    assert "urllib" not in imported
    assert "httpx" not in imported
    assert "requests" not in imported
    assert "skeleton.frontier" not in COMPOSITION_SOURCE
    assert "skeleton.platform" not in COMPOSITION_SOURCE
    assert "godot" not in COMPOSITION_SOURCE.lower()
    assert "not a replay engine" in COMPOSITION_SOURCE

    assert "class GameMechanicsGenerator" in MECHANICS_SOURCE
    assert "uuid.uuid4" in MECHANICS_SOURCE
    assert compose_gameplay is GameplayComposer.compose or callable(compose_gameplay)

    with pytest.raises(GameMechanicsError):
        ProgressionSystemSpec(style="linear", max_level=1001)
