from core.shift_supervisor.research_queries import derive_queries


def test_baseline_research_queries_prioritize_ci():
    queries = derive_queries({"repository": "Apeloff1/Skeleton"})
    assert queries
    assert queries[0].topic == "ci"
    assert all("Apeloff1/Skeleton" in q.query for q in queries)
