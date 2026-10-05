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

def test_manually_forged_complete_proof_is_rejected():
 from skeleton.vault.deletion_proof import DeletionProof
 with pytest.raises(LifecycleError,match="digest mismatch"):
  DeletionProof("r",("mongo",),("mongo",),"0"*64)

def test_deletion_proof_collections_must_be_canonical_and_bounded_to_required_set():
 from skeleton.vault.deletion_proof import DeletionProof
 import hashlib,json
 digest=lambda req:hashlib.sha256(json.dumps({"record":"r","required":req},sort_keys=True,separators=(",",":")).encode()).hexdigest()
 with pytest.raises(LifecycleError,match="sorted unique"):
  DeletionProof("r",("mongo","mongo"),("mongo",),digest(("mongo","mongo")))
 with pytest.raises(LifecycleError,match="subset"):
  DeletionProof("r",("mongo",),("mongo","other"),digest(("mongo",)))

def test_deletion_topology_inputs_are_strictly_typed():
 with pytest.raises(LifecycleError,match="typed tuple"):
  prove_deletion(record_id="r",canonical_store="mongo",derived_stores=[],deleted_stores=("mongo",))
 with pytest.raises(LifecycleError,match="deleted_stores must be tuple"):
  prove_deletion(record_id="r",canonical_store="mongo",derived_stores=(),deleted_stores=["mongo"])
