import pytest
from skeleton.vault.erasure_topology import DerivedStore,ErasureTopology,ErasureTopologyError
def topology():
 return ErasureTopology((DerivedStore("canonical",(),"memory"),DerivedStore("retrieval",("canonical",),"retrieval"),DerivedStore("cache",("retrieval",),"cache")))
def test_transitive_targets_cover_future_derivations():
 assert topology().targets_for("canonical")==("cache","memory","retrieval")
def test_complete_deletion_coverage_accepted():
 topology().require_coverage("canonical",("memory","retrieval","cache"))
def test_missing_derived_target_fails_closed():
 with pytest.raises(ErasureTopologyError):topology().require_coverage("canonical",("memory","retrieval"))
def test_unknown_parent_rejected():
 with pytest.raises(ErasureTopologyError):ErasureTopology((DerivedStore("x",("missing",),"x"),))
def test_cycle_rejected():
 with pytest.raises(ErasureTopologyError):ErasureTopology((DerivedStore("a",("b",),"a"),DerivedStore("b",("a",),"b")))
def test_self_derivation_rejected():
 with pytest.raises(ErasureTopologyError):DerivedStore("a",("a",),"a")
