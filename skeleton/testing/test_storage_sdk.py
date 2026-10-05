import pytest
from skeleton.persistence.storage_sdk import *
def test_declared_consistency_selects_store():assert StorageSDK((StoreHandle("ledger","strong",("transactions",)),)).open("ledger","strong").consistency=="strong"
def test_wrong_consistency_and_unsupported_transaction_fail():
 sdk=StorageSDK((StoreHandle("cache","eventual",()),))
 with pytest.raises(LookupError):sdk.open("cache","strong")
 with pytest.raises(ValueError):sdk.transaction(sdk.open("cache","eventual"),"k")

def test_unregistered_store_cannot_start_transaction():
 import pytest
 sdk=StorageSDK(())
 with pytest.raises(PermissionError):sdk.transaction(StoreHandle("x","strong",("transactions",)),"k")
