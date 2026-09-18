"""Regression coverage for system-level semantic lens roles."""

from __future__ import annotations

from skeleton.jeeves.agent.semantic_extreme_lenses import rare_semantic_definitions
from skeleton.jeeves.agent.semantic_lenses import SemanticRole


EXPECTED_SYSTEM_LENSES = {
    "possibility_space",
    "deckbuilding_interaction_graph",
    "mechanic_as_verb",
}


def test_semantic_role_system_is_public_enum_member():
    assert SemanticRole.SYSTEM.value == "system"


def test_extreme_system_lenses_construct_without_enum_failure():
    definitions = rare_semantic_definitions()
    by_key = {definition.spec.key: definition for definition in definitions}
    assert EXPECTED_SYSTEM_LENSES <= set(by_key)
    for key in EXPECTED_SYSTEM_LENSES:
        assert by_key[key].spec.role is SemanticRole.SYSTEM


def test_system_role_is_distinct_from_generic_structure():
    assert SemanticRole.SYSTEM is not SemanticRole.STRUCTURE
    assert SemanticRole.SYSTEM.value != SemanticRole.STRUCTURE.value


def test_rare_semantic_definition_keys_remain_unique():
    definitions = rare_semantic_definitions()
    keys = [definition.spec.key for definition in definitions]
    assert len(keys) == len(set(keys))


def test_every_extreme_definition_has_a_valid_semantic_role():
    definitions = rare_semantic_definitions()
    assert definitions
    assert all(isinstance(definition.spec.role, SemanticRole) for definition in definitions)
