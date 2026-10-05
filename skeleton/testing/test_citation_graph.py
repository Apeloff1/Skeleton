from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.research_evaluation import CitationEdge
from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    ResearchEvaluationAssuranceError,
    analyze_citation_target,
)


def test_citation_analytics_counts_independent_support_and_contradictions() -> None:
    report = analyze_citation_target(
        (
            CitationEdge("paper-a", "claim-1", "supports"),
            CitationEdge("paper-b", "claim-1", "replicates"),
            CitationEdge("paper-c", "claim-1", "contradicts"),
        ),
        target_id="claim-1",
    )
    assert report.support_count == 2
    assert report.independent_sources == ("paper-a", "paper-b")
    assert report.contradiction_sources == ("paper-c",)
    assert len(report.graph_digest) == 64


def test_duplicate_citation_edge_fails_closed() -> None:
    edge = CitationEdge("paper-a", "claim-1", "supports")
    with pytest.raises(ResearchEvaluationAssuranceError, match="duplicate"):
        analyze_citation_target((edge, edge), target_id="claim-1")
