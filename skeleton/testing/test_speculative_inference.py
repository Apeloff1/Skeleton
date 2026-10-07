from skeleton.ai.speculative_inference import *
def test_draft_token_never_accepted_without_target_match():
 s=verify(SpeculativePlan("d","t",2),(DraftToken(1,.9),DraftToken(2,.9)),(1,3));assert accepted_tokens(s)==(1,) and not s[-1].accepted
def test_target_verification_is_explicit():assert verify(SpeculativePlan("d","t",1),(DraftToken(1,1),),(1,))[0].target_token==1

def test_target_must_verify_every_attempted_draft():
 import pytest
 p=SpeculativePlan("d","t",2)
 with pytest.raises(ValueError):verify(p,(DraftToken(1,.5),DraftToken(2,.5)),(1,))
def test_max_tokens_bounds_verification():assert len(verify(SpeculativePlan("d","t",1),(DraftToken(1,.5),DraftToken(2,.5)),(1,2)))==1
