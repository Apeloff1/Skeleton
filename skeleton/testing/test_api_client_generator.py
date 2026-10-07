import pytest
from skeleton.ai.api_client_generator import *
OPS=({"api_version":"v1","name":"get","method":"GET","path":"/x","auth_required":True},)
def test_client_is_bound_to_exact_contract_and_auth():assert check_compatibility(generate_client("v1",OPS),OPS)
def test_version_drift_and_missing_auth_fail_closed():
 with pytest.raises(ValueError):generate_client("v2",OPS)
 with pytest.raises(ValueError):generate_client("v1",({"api_version":"v1","name":"x","method":"GET","path":"/x"},))
def test_stub_drift_detected():assert not check_compatibility(generate_client("v1",OPS),({"api_version":"v1","name":"get","method":"POST","path":"/x","auth_required":True},))

def test_duplicate_operations_rejected():
 import pytest
 op={"api_version":"v1","name":"x","method":"GET","path":"/x","auth_required":True}
 with pytest.raises(ValueError):generate_client("v1",(op,op))
def test_auth_must_be_boolean():
 import pytest
 with pytest.raises(ValueError):generate_client("v1",({"api_version":"v1","name":"x","method":"GET","path":"/x","auth_required":1},))

def test_server_missing_auth_semantics_is_incompatible():
 c=generate_client("v",({"api_version":"v","name":"x","method":"GET","path":"/x","auth_required":True},))
 assert not check_compatibility(c,({"api_version":"v","name":"x","method":"GET","path":"/x"},))
