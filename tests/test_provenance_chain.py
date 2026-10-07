"""A grandchild stays on the original provenance chain."""

from skeleton.retrieval.provenance import ProvenanceLedger


def test_trace_follows_parents_to_the_root() -> None:
    ledger = ProvenanceLedger()
    first = ledger.record("ingest", "extract", "raw", "A")
    second = ledger.record("ingest", "link", "A", "B", parent_id=first.entry_id)
    third = ledger.record("ingest", "link", "B", "C", parent_id=second.entry_id)
    assert [entry.entry_id for entry in ledger.trace(third.entry_id)] == [
        first.entry_id,
        second.entry_id,
        third.entry_id,
    ]
