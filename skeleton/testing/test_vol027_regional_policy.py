import pytest
from skeleton.vault.erasure_topology import ErasureTopologyError
from skeleton.vault.regional_policy import RegionalPrivacyPolicy,RegionalPolicyMap
def policies():return RegionalPolicyMap((RegionalPrivacyPolicy("EEA",("inference","support"),False,True),RegionalPrivacyPolicy("US",("inference","support"),True,True)))
def test_region_resolves_exact_policy():assert policies().require("eea","inference").deletion_required
def test_unknown_region_fails_closed():
 with pytest.raises(ErasureTopologyError):policies().require("unknown","inference")
def test_unregistered_purpose_denied():
 with pytest.raises(ErasureTopologyError):policies().require("EEA","advertising")
def test_export_policy_enforced():
 with pytest.raises(ErasureTopologyError):policies().require("EEA","support",export=True)
 assert policies().require("US","support",export=True).export_allowed
def test_duplicate_region_rejected():
 p=RegionalPrivacyPolicy("EEA",("support",),False,True)
 with pytest.raises(ErasureTopologyError):RegionalPolicyMap((p,p))
