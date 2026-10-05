import pytest
from skeleton.vault.erasure_topology import ErasureTopologyError
from skeleton.vault.regional_policy import RegionalPolicyMap,RegionalPrivacyPolicy
def policies():return RegionalPolicyMap((RegionalPrivacyPolicy("EEA",("assist",),("EEA",),False,True,30),RegionalPrivacyPolicy("US",("assist","analytics"),("US","EEA"),True,True,90)))
def test_region_allows_bounded_local_processing():assert policies().require("eea","assist",transfer_region="EEA",retention_days=30).deletion_required
def test_unknown_region_fails_closed():
 with pytest.raises(ErasureTopologyError):policies().require("XX","assist")
def test_purpose_export_transfer_and_retention_denials():
 p=policies()
 for kwargs in ({"purpose":"analytics"},{"purpose":"assist","export":True},{"purpose":"assist","transfer_region":"US"},{"purpose":"assist","retention_days":31}):
  with pytest.raises(ErasureTopologyError):p.require("EEA",**kwargs)
def test_duplicate_region_rejected():
 x=RegionalPrivacyPolicy("EEA",("assist",),("EEA",),False,True,30)
 with pytest.raises(ErasureTopologyError):RegionalPolicyMap((x,x))
