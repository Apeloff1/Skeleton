"""Semantic-role catalog compatibility for frontier extreme lenses."""

from skeleton.jeeves.agent.semantic_extreme_lenses import rare_semantic_definitions
from skeleton.jeeves.agent.semantic_lenses import SemanticRole


def test_every_extreme_lens_uses_declared_semantic_role():
    definitions = rare_semantic_definitions()
    assert definitions
    declared = set(SemanticRole)
    assert all(item.spec.role in declared for item in definitions)


def test_system_semantic_role_is_available_for_system_lenses():
    assert SemanticRole.SYSTEM.value == "system"
    system_lenses = [
        item
        for item in rare_semantic_definitions()
        if item.spec.role is SemanticRole.SYSTEM
    ]
    assert system_lenses
