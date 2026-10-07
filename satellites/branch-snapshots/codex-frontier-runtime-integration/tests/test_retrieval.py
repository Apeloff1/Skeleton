"""Tests for retrieval provenance and reranking."""

from skeleton.retrieval.provenance import ProvenanceLedger
from skeleton.retrieval.reranker import Reranker


class TestProvenance:
    def test_constructs(self):
        assert ProvenanceLedger() is not None


class TestReranker:
    def test_constructs(self):
        assert Reranker() is not None
