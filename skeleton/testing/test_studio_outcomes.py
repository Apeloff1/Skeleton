import pytest
from skeleton.automation.studio_outcomes import OutcomeReceipt, verify_outcome

def receipt():
    return OutcomeReceipt("a"*64,"b"*24,"task","lane","c"*64,"d"*64,True,(("python","-m","pytest"),))

def test_outcome_digest_is_deterministic():
    assert receipt().digest()==receipt().digest()

def test_outcome_binds_allocation():
    verify_outcome(receipt().payload(),"a"*64)
    with pytest.raises(ValueError,match="allocation"): verify_outcome(receipt().payload(),"f"*64)

def test_outcome_rejects_bad_diff_digest():
    p=receipt().payload(); p["applied_diff_sha256"]="bad"
    with pytest.raises(ValueError,match="applied"): verify_outcome(p,"a"*64)
