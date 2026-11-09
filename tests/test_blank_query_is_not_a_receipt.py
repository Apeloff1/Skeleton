"""A blank query is not a receipt, and a missing fragment has no planes."""

import pytest

from skeleton.retrieval.receipts import RetrievalReceipt, query_digest


def _payload() -> dict:
    return {
        "receipt_id": "r1",
        "query_digest": query_digest("alpha"),
        "generation": 1,
        "scope_digest": "",
        "considered_planes": ["rag"],
        "candidate_planes": ["rag"],
        "failed_planes": [],
        "fragment_planes": [{"fragment_id": "doc", "planes": ["rag"]}],
        "partial": False,
        "created_ns": 1,
        "source": "live",
    }


def test_blank_query_and_missing_source_raise() -> None:
    with pytest.raises(ValueError):
        query_digest("   ")
    payload = _payload()
    del payload["source"]
    with pytest.raises(ValueError):
        RetrievalReceipt.from_dict(payload)
    receipt = RetrievalReceipt.from_dict(_payload())
    assert receipt.planes_for_fragment("doc") == ("rag",)
    with pytest.raises(KeyError):
        receipt.planes_for_fragment("missing")
