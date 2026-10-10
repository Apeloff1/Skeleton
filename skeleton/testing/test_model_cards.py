from __future__ import annotations
import hashlib,pytest
from skeleton.ai.governance.cards import GovernanceCardError,ModelCard
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_model_card_binds_mbom_and_eval():
    card=ModelCard("c","m","a"*40,d("mbom"),d("eval"),("chat",),("weapons",),("offline quality varies",))
    assert len(card.digest)==64 and card.promotion_authority is False
def test_model_card_use_sets_must_be_disjoint():
    with pytest.raises(GovernanceCardError,match="disjoint"):
        ModelCard("c","m","a"*40,d("m"),d("e"),("x",),("x",),("l",))
def test_model_card_cannot_self_promote():
    with pytest.raises(GovernanceCardError,match="cannot grant"):
        ModelCard("c","m","a"*40,d("m"),d("e"),("x",),("y",),("l",),True)
