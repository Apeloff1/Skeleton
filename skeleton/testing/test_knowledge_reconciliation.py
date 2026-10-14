import pytest
from skeleton.ai.knowledge_reconciliation import *
def case():return ReconciliationCase("r",KnowledgeConflict(("a","b"),("e1","e2")))
def test_disagreement_can_remain_explicit():assert reconcile(case(),"unresolved").competing_evidence==("e1","e2")
def test_popularity_or_arbitrary_winner_is_not_rule():
 with pytest.raises(ValueError):reconcile(case(),"popular","a")
 with pytest.raises(ValueError):reconcile(case(),"unresolved","a")

def test_verified_supersession_without_evidence_rejected():
 import pytest
 c=ReconciliationCase("c",KnowledgeConflict(("a","b"),()))
 with pytest.raises(PermissionError):reconcile(c,"verified-supersession","a")
