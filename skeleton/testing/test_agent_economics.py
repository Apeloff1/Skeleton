from decimal import Decimal
import pytest
from skeleton.ai.agents.economics import AgentCost, AgentCostLedger, AgentEconomicsError, AgentOffer, choose_offer

def test_cost_ledger_rejects_duplicate_evidence():
    ledger=AgentCostLedger()
    cost=AgentCost("a","t","d",Decimal("1.25"),"USD","receipt:1")
    ledger.record(cost)
    with pytest.raises(AgentEconomicsError, match="duplicate"):
        ledger.record(cost)

def test_cost_ledger_attributes_task_and_delegation():
    ledger=AgentCostLedger()
    ledger.record(AgentCost("a","t","d",Decimal("1.25"),"USD","r1"))
    ledger.record(AgentCost("b","t","d",Decimal("2.00"),"USD","r2"))
    assert ledger.total_for_task("t","USD")==Decimal("3.25")
    assert ledger.total_for_delegation("d","USD")==Decimal("3.25")

def test_cheaper_offer_cannot_weaken_quality_or_authority():
    offers=[
        AgentOffer("cheap",Decimal("1"),Decimal("0.4"),"reduced","full"),
        AgentOffer("safe",Decimal("3"),Decimal("0.95"),"bounded","full"),
    ]
    decision=choose_offer("t",offers,quality_floor=Decimal("0.9"),required_authority_profile="bounded",required_verification_profile="full")
    assert decision.selected_agent=="safe"

def test_cheaper_offer_cannot_weaken_verification():
    offers=[AgentOffer("cheap",Decimal("1"),Decimal("0.99"),"bounded","none")]
    with pytest.raises(AgentEconomicsError, match="no offer"):
        choose_offer("t",offers,quality_floor=Decimal("0.9"),required_authority_profile="bounded",required_verification_profile="full")

def test_tie_break_is_deterministic():
    offers=[
        AgentOffer("b",Decimal("2"),Decimal("0.95"),"bounded","full"),
        AgentOffer("a",Decimal("2"),Decimal("0.95"),"bounded","full"),
    ]
    d=choose_offer("t",offers,quality_floor=Decimal("0.9"),required_authority_profile="bounded",required_verification_profile="full")
    assert d.selected_agent=="a"
