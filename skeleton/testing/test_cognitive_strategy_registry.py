import pytest
from skeleton.ai.cognitive_strategy import *
def test_untested_strategy_cannot_promote():
 with pytest.raises(PermissionError):promote(CognitiveStrategy("x",StrategyVersion("v1"),()))
def test_evidence_bound_promotion():assert promote(CognitiveStrategy("x",StrategyVersion("v1"),(StrategyEvidence("b",True),))).production

def test_direct_production_construction_requires_evidence():
 import pytest
 with pytest.raises(PermissionError):CognitiveStrategy("s",StrategyVersion("v"),(),True)
