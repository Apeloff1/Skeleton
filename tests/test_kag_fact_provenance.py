"""Structured KAG facts keep the confidence and provenance they were given."""

import pytest

from skeleton.retrieval.quad import QuadRetriever


def test_ingest_fact_keeps_confidence_and_provenance() -> None:
    quad = QuadRetriever()
    quad.ingest_fact("Ada", "wrote", "Notes", confidence=0.25, provenance="journal:12")

    note = quad._planes["kag"].graph.annotation_for("Ada", "wrote", "Notes")
    assert note.confidence == 0.25
    assert note.provenance == "journal:12"

    direct = quad._planes["kag"].query("ada")
    assert direct[0].provenance == "journal:12"
    assert direct[0].metadata["confidence"] == 0.25
    assert direct[0].score == pytest.approx(0.25)

    fused = quad.retrieve("ada", use_cache=False)
    assert any(item.provenance == "journal:12" for item in fused)


def test_stronger_replay_keeps_confidence_and_fills_empty_provenance() -> None:
    quad = QuadRetriever()
    quad.ingest_fact("Ada", "wrote", "Notes", confidence=0.2, provenance="")
    quad.ingest_fact("Ada", "wrote", "Notes", confidence=0.8, provenance="ledger:9")
    quad.ingest_fact("Ada", "wrote", "Notes", confidence=0.1, provenance="")

    note = quad._planes["kag"].graph.annotation_for("ada", "wrote", "notes")
    assert note.confidence == 0.8
    assert note.provenance == "ledger:9"


def test_ingest_fact_rejects_confidence_outside_unit_interval() -> None:
    quad = QuadRetriever()
    with pytest.raises(ValueError):
        quad.ingest_fact("Ada", "wrote", "Notes", confidence=1.5)
    assert "kag" not in quad._planes
