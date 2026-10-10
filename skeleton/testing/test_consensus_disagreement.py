import pytest
from skeleton.ai.agents.consensus import ConsensusError, DecisionStatus, ConsensusProposal, decide

def p(r,g,c,impact="normal"):
    return ConsensusProposal(r,g,c,0.9,(f"evidence:{r}",),impact)

def test_requires_independent_review_groups():
    d=decide([p("a","same","ship"),p("b","same","ship")])
    assert d.status is DecisionStatus.INSUFFICIENT_INDEPENDENCE
    assert d.selected_choice is None

def test_high_impact_dissent_escalates_even_with_majority():
    d=decide([p("a","g1","ship"),p("b","g2","ship"),p("c","g3","block","critical")])
    assert d.status is DecisionStatus.ESCALATE
    assert d.selected_choice is None
    assert d.dissent[0].high_impact

def test_preserves_dissent_evidence_on_valid_consensus():
    d=decide([p("a","g1","ship"),p("b","g2","ship"),p("c","g3","block")])
    assert d.status is DecisionStatus.CONSENSUS
    assert d.selected_choice=="ship"
    assert d.dissent[0].evidence_refs==("evidence:c",)

def test_duplicate_reviewer_cannot_amplify_vote():
    with pytest.raises(ConsensusError, match="only once"):
        decide([p("a","g1","ship"),p("a","g2","ship")])

def test_proposal_requires_evidence():
    with pytest.raises(ConsensusError, match="evidence"):
        ConsensusProposal("a","g1","ship",0.8,())
