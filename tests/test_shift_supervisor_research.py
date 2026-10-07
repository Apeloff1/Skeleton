from core.shift_supervisor.research import ResearchBroker


def test_research_broker_isolates_failed_source_and_preserves_success():
    def good(_context):
        yield {"summary": "useful", "refs": ["source:a"]}

    def bad(_context):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    broker = ResearchBroker({"good": good, "bad": bad})
    records = broker.collect({"repo": "Skeleton"})

    assert any(record.get("summary") == "useful" and record.get("source") == "good" for record in records)
    assert any(record.get("source") == "bad" and record.get("error") == "RuntimeError" for record in records)


def test_research_broker_bounds_results_per_source():
    broker = ResearchBroker({"many": lambda _context: ({"n": i} for i in range(100))})
    records = broker.collect({}, per_source_limit=3)
    assert [record["n"] for record in records] == [0, 1, 2]
