from __future__ import annotations
import hashlib,pytest
from skeleton.ai.governance.cards import AgentCard,GovernanceCardError
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_agent_card_binds_performance_authority_and_human_control():
    card=AgentCard("c","agent","d"*40,d("registry"),d("perf"),d("authority"),d("human"),("read","plan"))
    assert card.autonomous_side_effects is False and card.promotion_authority is False
def test_agent_card_cannot_authorize_autonomous_side_effects():
    with pytest.raises(GovernanceCardError,match="autonomous side effects"):
        AgentCard("c","a","d"*40,d("r"),d("p"),d("a"),d("h"),("x",),True)
