import pytest
from skeleton.ai.research_branching import *
def test_research_branch_cannot_bypass_production_gates():
 p=ResearchBranchPolicy("research/","o",("ci","security"));c=ResearchMergeCandidate(ResearchBranch("research/x","sha","e","o"),("ev",),frozenset({"ci"}))
 with pytest.raises(PermissionError):promote(c,p)
def test_lineage_and_evidence_allow_promotion():assert promote(ResearchMergeCandidate(ResearchBranch("research/x","sha","e","o"),("ev",),frozenset({"ci"})),ResearchBranchPolicy("research/","o",("ci",)))

def test_duplicate_promotion_evidence_rejected():
 import pytest
 p=ResearchBranchPolicy("r/","o",("g",));b=ResearchBranch("r/x","sha","e","o")
 with pytest.raises(ValueError):promote(ResearchMergeCandidate(b,("x","x"),frozenset({"g"})),p)
