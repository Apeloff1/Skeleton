from __future__ import annotations

from skeleton.ai.runtime.deferred.deployment_operations_assurance import ResearchDashboardEvidence

A="a"*64
B="b"*64
C="c"*64

def test_research_dashboard_binds_backlog_citation_and_experiment_graphs()->None:
    evidence=ResearchDashboardEvidence(A,B,C,7)
    assert evidence.research_backlog_digest==A
    assert evidence.citation_graph_digest==B
    assert evidence.experiment_graph_digest==C
    assert evidence.production_authority is False
    assert len(evidence.digest)==64
