from skeleton.masterplan.closure import ClosureReject, close_all, close_gap, open_gaps


def test_every_open_gap_closes_and_rejects_foreign_card() -> None:
    rows = open_gaps()
    assert rows
    receipts = close_all()
    assert len(receipts) == len(rows)
    assert all(row["closed"] and row["stored_prose"] == 0 for row in receipts)
    sample = rows[0]
    try:
        close_gap(sample["volume"], "not-the-gap", {
            "volume": sample["volume"],
            "gap_digest": sample["digest"],
            "owner": "wave5",
            "bound": 64,
            "evidence": "skeleton/masterplan/closure.py",
        })
        raise AssertionError("foreign gap text must not close")
    except ClosureReject as exc:
        assert exc.reason == "gap digest mismatch"
