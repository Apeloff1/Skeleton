import pytest
from skeleton.ai.providers.provider_migration import *

def test_data_boundary_regression_blocks_cutover():
    with pytest.raises(PermissionError):
        cutover(ProviderMigration("a","b",ProviderParity(True,True,True,True,False)))

def test_cutover_preserves_rollback_target():
    assert cutover(ProviderMigration("a","b",ProviderParity(True,True,True,True,True),"canary")).rollback == "a"

def test_integer_parity_assertion_rejected():
    with pytest.raises(ValueError):
        cutover(ProviderMigration("a","b",ProviderParity(1,True,True,True,True)))
