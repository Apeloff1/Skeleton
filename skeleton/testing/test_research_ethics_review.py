from skeleton.eval.research_ethics import *
def test_technical_success_cannot_substitute_for_review():
 r=EthicsReview("r",ResearchRisk(True,False,False),False,None);assert not decide(r).approved
def test_sensitive_research_requires_oversight():assert not decide(EthicsReview("r",ResearchRisk(False,True,False),True,None)).approved

def test_nonboolean_risk_assertion_denied():assert not decide(EthicsReview("r",ResearchRisk(1,False,False),True,"o")).approved
