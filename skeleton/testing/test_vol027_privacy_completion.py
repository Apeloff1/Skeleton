import pytest
from skeleton.vault.data_lifecycle import LifecycleError
from skeleton.vault.deletion_proof import DerivedStore,prove_deletion,require_complete_deletion
from skeleton.vault.regional_privacy import policy_for_region,registered_regions
def test_transitive_derived_stores_are_required():
 stores=(DerivedStore("retrieval",("mongo",)),DerivedStore("cache",("retrieval",)),DerivedStore("analytics",("mongo",)))
 p=prove_deletion(record_id="r",canonical_store="mongo",derived_stores=stores,deleted_stores=("mongo","retrieval","cache","analytics"))
 assert p.complete and p.required_stores==("analytics","cache","mongo","retrieval")
def test_missing_future_projection_fails_completion():
 p=prove_deletion(record_id="r",canonical_store="mongo",derived_stores=(DerivedStore("future-index",("mongo",)),),deleted_stores=("mongo",))
 with pytest.raises(LifecycleError):require_complete_deletion(p)
def test_unknown_receipt_store_rejected():
 with pytest.raises(LifecycleError):prove_deletion(record_id="r",canonical_store="mongo",derived_stores=(),deleted_stores=("mongo","other"))
def test_self_derived_store_rejected():
 with pytest.raises(LifecycleError):DerivedStore("x",("x",))
@pytest.mark.parametrize("region,framework",[("EEA","GDPR"),("uk","UK-GDPR"),("US-CA","CCPA-CPRA"),("global","baseline")])
def test_regional_policy_mapping(region,framework):
 assert policy_for_region(region).framework==framework
def test_unknown_region_fails_closed():
 with pytest.raises(LifecycleError):policy_for_region("unknown")
def test_registry_is_deterministic():
 assert registered_regions()==("EEA","GLOBAL","UK","US-CA")
