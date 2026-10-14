import pytest
from skeleton.ai.providers.provider_migration import *


def parity():
    return ProviderParity(True, True, True, True, True)


def test_data_boundary_regression_blocks_cutover():
    with pytest.raises(PermissionError):
        cutover(
            ProviderMigration(
                "a",
                "b",
                ProviderParity(True, True, True, True, False),
                "canary",
            )
        )


def test_cutover_preserves_rollback_target():
    assert cutover(
        ProviderMigration("a", "b", parity(), "canary")
    ).rollback == "a"


def test_integer_parity_assertion_rejected():
    with pytest.raises(ValueError):
        ProviderParity(1, True, True, True, True)


def test_shadow_cannot_cut_over_directly():
    migration = ProviderMigration("a", "b", parity(), "shadow")
    with pytest.raises(PermissionError):
        cutover(migration)


def test_shadow_promotes_to_canary_before_cutover():
    canary = promote_to_canary(
        ProviderMigration("a", "b", parity(), "shadow")
    )
    assert canary.stage == "canary"
    receipt = cutover(canary)
    assert receipt.active == "b"


def test_rollback_restores_previous_active_provider():
    receipt = cutover(
        ProviderMigration("a", "b", parity(), "canary")
    )
    restored = rollback(receipt)
    assert restored.active == "a"
    assert restored.rollback == "b"
