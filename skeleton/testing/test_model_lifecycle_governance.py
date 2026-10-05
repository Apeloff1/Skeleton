import pytest
from skeleton.ai.providers.model_lifecycle import *
def e():return ModelGovernanceEvidence("e","owner","rollback","retain")
def test_invalid_transition_rejected():
 with pytest.raises(ValueError):transition(ModelLifecycle("m","intake",()),"operation",e())
def test_transition_requires_governance_evidence():assert transition(ModelLifecycle("m","intake",()),"training",e()).state=="training"

def test_duplicate_governance_evidence_rejected():
 import pytest
 e=ModelGovernanceEvidence("e","o","r","keep");m=ModelLifecycle("m","training",(e,))
 with pytest.raises(ValueError):transition(m,"evaluation",e)
