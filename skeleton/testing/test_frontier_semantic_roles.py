from skeleton.jeeves.agent.semantic_lenses import SemanticRole


def test_frontier_semantic_catalog_roles_are_import_safe() -> None:
    assert SemanticRole.SYSTEM.value == "system"
    assert SemanticRole.SOCIAL.value == "social"
    assert SemanticRole.TEMPORAL.value == "temporal"
