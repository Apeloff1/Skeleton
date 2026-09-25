"""A provenance record cannot name a parent that was never recorded."""

import pytest

from skeleton.retrieval.provenance import ProvenanceLedger


def test_blank_source_and_missing_parent_raise() -> None:
    ledger = ProvenanceLedger()
    with pytest.raises(ValueError):
        ledger.record("  ", "extract", "raw", "A")
    with pytest.raises(ValueError):
        ledger.record("ingest", "extract", "raw", "A", parent_id="missing")
    with pytest.raises(KeyError):
        ledger.trace("missing")
    with pytest.raises(KeyError):
        ledger.verify("missing", "A")
    entry = ledger.record("ingest", "extract", "raw", "A")
    assert ledger.verify(entry.entry_id, "A") is True
    assert ledger.verify(entry.entry_id, "B") is False
