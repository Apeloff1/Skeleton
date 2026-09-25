"""Retrieval receipts bind learning feedback to actual returned evidence."""

import copy

import pytest

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.quad import QuadRetriever
from skeleton.retrieval.receipts import ReceiptLedger, RetrievalReceipt, query_digest


class _Plane:
    def __init__(self, plane: str) -> None:
        self.plane = plane
        self.calls = 0

    def query(self, query: str, top_k: int):
        self.calls += 1
        return [
            ScoredResult(
                fragment_id=f"{self.plane}-1",
                content=f"{query}:{self.plane}",
                score=1.0,
                plane=self.plane,
                provenance=f"test:{self.plane}",
            )
        ]


def test_receipt_carries_hashes_and_candidate_lineage_without_query_text() -> None:
    quad = QuadRetriever()
    quad.register_plane("rag", _Plane("rag"))
    quad.register_plane("kag", _Plane("kag"))

    results, receipt = quad.retrieve_with_receipt("private query", k=4, use_cache=False)

    assert {item.fragment_id for item in results} == {"rag-1", "kag-1"}
    assert receipt.query_digest == query_digest("private query")
    assert "private query" not in repr(receipt.to_dict())
    assert receipt.considered_planes == ("rag", "kag")
    assert set(receipt.candidate_planes) == {"rag", "kag"}
    assert set(receipt.fragment_ids) == {"rag-1", "kag-1"}
    assert receipt.partial is False
    assert receipt.source == "live"


def test_cache_hit_mints_a_new_receipt_without_requerying() -> None:
    plane = _Plane("rag")
    quad = QuadRetriever()
    quad.register_plane("rag", plane)

    _, first = quad.retrieve_with_receipt("same")
    _, second = quad.retrieve_with_receipt("same")

    assert plane.calls == 1
    assert first.receipt_id != second.receipt_id
    assert first.query_digest == second.query_digest
    assert first.source == "live"
    assert second.source == "cache"


def test_attributed_feedback_consumes_receipt_exactly_once() -> None:
    quad = QuadRetriever()
    quad.register_plane("rag", _Plane("rag"))
    quad.register_plane("kag", _Plane("kag"))
    _, receipt = quad.retrieve_with_receipt("learn", use_cache=False)

    before = dict(quad.weights)
    stats = quad.observe_receipt(receipt.receipt_id, ["kag-1"])

    assert stats["updates"] == 1
    assert quad.weights["kag"] > before["kag"]
    assert quad.weights["rag"] < before["rag"]
    assert quad.stats()["feedback_consumed"] == 1
    with pytest.raises(ValueError, match="already consumed"):
        quad.observe_receipt(receipt.receipt_id, ["kag-1"])


def test_feedback_cannot_name_fragment_not_returned_by_receipt() -> None:
    quad = QuadRetriever()
    quad.register_plane("rag", _Plane("rag"))
    _, receipt = quad.retrieve_with_receipt("learn", use_cache=False)

    with pytest.raises(ValueError, match="absent from receipt"):
        quad.observe_receipt(receipt.receipt_id, ["invented-fragment"])
    assert quad.stats()["feedback_consumed"] == 0


def test_consumed_feedback_authority_survives_restart() -> None:
    quad = QuadRetriever()
    quad.register_plane("rag", _Plane("rag"))
    _, receipt = quad.retrieve_with_receipt("restart", use_cache=False)
    quad.observe_receipt(receipt.receipt_id, ["rag-1"])
    checkpoint = quad.export_retrieval_state()

    restored = QuadRetriever()
    restored.restore_retrieval_state(copy.deepcopy(checkpoint))

    assert restored.export_retrieval_state() == checkpoint
    with pytest.raises(ValueError, match="already consumed"):
        restored.observe_receipt(receipt.receipt_id, ["rag-1"])


def test_receipt_ledger_is_bounded_and_checkpoint_validated() -> None:
    ledger = ReceiptLedger(max_entries=2)
    rows = []
    for index in range(3):
        receipt = RetrievalReceipt(
            receipt_id=f"r{index}",
            query_digest=f"q{index}",
            generation=0,
            scope_digest="",
            considered_planes=("rag",),
            candidate_planes=("rag",),
            failed_planes=(),
            fragment_planes=((f"f{index}", ("rag",)),),
            partial=False,
            created_ns=index,
        )
        ledger.record(receipt)
        rows.append(receipt)

    assert ledger.get("r0") is None
    assert [row.receipt_id for row in ledger.recent(10)] == ["r1", "r2"]

    state = ledger.snapshot()
    restored = ReceiptLedger.from_snapshot(copy.deepcopy(state))
    assert restored.snapshot() == state

    broken = copy.deepcopy(state)
    broken["consumed"] = ["missing"]
    with pytest.raises(ValueError, match="no retained receipt"):
        ReceiptLedger.from_snapshot(broken)
