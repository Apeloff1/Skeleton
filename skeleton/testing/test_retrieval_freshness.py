from skeleton.retrieval.freshness_policy import *
def test_cache_age_alone_cannot_claim_freshness():assert not decide_freshness(FreshnessRequirement(60,10,"refresh"),FreshnessState(1,9,True)).fresh
def test_invalid_source_abstains():assert decide_freshness(FreshnessRequirement(60,1,"abstain"),FreshnessState(1,1,False)).action=="abstain"
