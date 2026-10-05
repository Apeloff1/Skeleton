from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.research.citation_graph import CitationEdge,CitationGraph,CitationGraphError,CitationNode

def d(x): return hashlib.sha256(x.encode()).hexdigest()

def test_citation_graph_counts_inbound_citations():
    graph=CitationGraph(
        "g",
        (CitationNode("a",d("a"),2024),CitationNode("b",d("b"),2025),CitationNode("c",d("c"),2025)),
        (CitationEdge("b","a"),CitationEdge("c","a")),
    )
    assert graph.inbound_counts()=={"a":2,"b":0,"c":0}
    assert len(graph.digest)==64

def test_unknown_citation_target_is_rejected():
    with pytest.raises(CitationGraphError,match="unknown work"):
        CitationGraph("g",(CitationNode("a",d("a"),2024),),(CitationEdge("a","missing"),))

def test_self_citation_is_rejected():
    with pytest.raises(CitationGraphError,match="self-reference"):
        CitationEdge("a","a")

def test_duplicate_edges_are_rejected():
    edge=CitationEdge("b","a")
    with pytest.raises(CitationGraphError,match="edges must be unique"):
        CitationGraph("g",(CitationNode("a",d("a"),2024),CitationNode("b",d("b"),2025)),(edge,edge))
