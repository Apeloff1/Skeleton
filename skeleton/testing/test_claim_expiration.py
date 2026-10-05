from skeleton.ai.claim_expiration import *
def test_expiration_keeps_lineage_for_revalidation():
 v=ClaimValidity("c",0,ExpirationPolicy(10,"normal"),"lineage");r=revalidation(v,11);assert r.lineage_id=="lineage"
def test_high_volatility_expires_more_strictly():
 assert not valid_at(ClaimValidity("c",0,ExpirationPolicy(10,"high"),"l"),6)
