from skeleton.school.cs_pathways import next_pathway
from skeleton.school.epistemics import EpistemicEngine, EpistemicEvidence, EvidencePolarity


def test_epistemic_supersession_replaces_active_evidence() -> None:
    engine = EpistemicEngine()
    engine.observe(EpistemicEvidence("old", "claim", EvidencePolarity.SUPPORTS))
    update = engine.observe(EpistemicEvidence("new", "claim", EvidencePolarity.REFUTES, supersedes=("old",)))
    assert update.belief.evidence_ids == ("new",)
    assert update.belief.confidence < 0.5
    assert tuple(item.evidence_id for item in engine.active_evidence("claim")) == ("new",)


def test_cs_pathway_prerequisites_form_a_reachable_graph() -> None:
    first = next_pathway((), interests=("graphs",))
    assert first is not None and first.pathway_id == "arrays_to_pools"
    graph = next_pathway(("arrays_to_pools",), interests=("graphs",))
    assert graph is not None and graph.pathway_id == "graphs"
    pathfinding = next_pathway(("arrays_to_pools", "graphs"))
    assert pathfinding is not None and pathfinding.pathway_id == "graphs_to_pathfinding"
