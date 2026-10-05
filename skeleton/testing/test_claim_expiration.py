from skeleton.ai.claim_expiration import *
def test_expiration_keeps_lineage_for_revalidation():
 v=ClaimValidity("c",0,ExpirationPolicy(10,"normal"),"lineage");r=revalidation(v,11);assert r.lineage_id=="lineage"
def test_high_volatility_expires_more_strictly():
 assert not valid_at(ClaimValidity("c",0,ExpirationPolicy(10,"high"),"l"),6)

def test_future_observation_is_not_valid():assert not valid_at(ClaimValidity("c",10,ExpirationPolicy(5,"normal"),"l"),9)
def test_nonpositive_ttl_rejected():
 import pytest
 with pytest.raises(ValueError):ExpirationPolicy(0,"normal")

def test_negative_observation_and_evaluation_time_rejected():
 import pytest
 with pytest.raises(ValueError):ClaimValidity("c",-1,ExpirationPolicy(1,"low"),"l")
 v=ClaimValidity("c",0,ExpirationPolicy(1,"low"),"l")
 with pytest.raises(ValueError):valid_at(v,-1)
