from skeleton.masterplan.ledger_tail import TailReject, catalog_ids, close_item, close_tail, p1_ids


def test_tail_closes_catalog_and_p1() -> None:
    receipts = close_tail()
    assert len(catalog_ids()) == 240
    assert len(p1_ids()) == 44
    assert len(receipts) == 284
    assert all(row["closed"] and row["stored_prose"] == 0 for row in receipts)
    try:
        close_item("catalog", catalog_ids()[0], {
            "kind": "catalog", "id": "OTHER", "owner": "wave6", "bound": 32,
            "evidence": "skeleton/masterplan/ledger_tail.py",
        })
        raise AssertionError("foreign id must fail")
    except TailReject as exc:
        assert exc.reason == "identity mismatch"
