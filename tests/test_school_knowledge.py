from skeleton.school.knowledge import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, KnowledgeState, RelationKind, infer_ready_frontier, rank_knowledge


def test_knowledge_graph_tracks_prerequisites_and_frontier():
    graph = KnowledgeGraph()
    graph.add_node(KnowledgeNode("variables", "Variables", tags=("python",)))
    graph.add_node(KnowledgeNode("loops", "Loops", tags=("python", "control-flow")))
    graph.add_node(KnowledgeNode("algorithms", "Algorithms", tags=("cs",)))
    graph.add_edge(KnowledgeEdge("loops", "variables", RelationKind.PREREQUISITE))
    graph.add_edge(KnowledgeEdge("algorithms", "loops", RelationKind.PREREQUISITE))
    graph.validate()

    state = KnowledgeState()
    state.observe("variables", 0.95, evidence="independent exercise")
    assert infer_ready_frontier(graph, state) == ("loops",)
    assert graph.ancestors("algorithms") == ("loops", "variables")


def test_knowledge_ranking_prioritizes_misconception_repair():
    graph = KnowledgeGraph()
    graph.add_node(KnowledgeNode("sorting", "Sorting", description="ordering arrays"))
    graph.add_node(KnowledgeNode("search", "Binary Search", description="ordered lookup"))
    state = KnowledgeState()
    state.mark_misconception("sorting", "confuses stable ordering")
    candidates = rank_knowledge(graph, state, query_terms=("sorting",))
    assert candidates[0].node_id == "sorting"
    assert candidates[0].reason == "misconception repair"
