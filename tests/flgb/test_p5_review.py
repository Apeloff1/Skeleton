from skeleton.p5.review import OPEN_FINDINGS, run_review


def test_review_holds_probes_and_keeps_findings_open() -> None:
    report = run_review()
    assert report["probes_held"] == 4
    assert report["clean"] is False
    assert report["stored_prose"] == 0
    ids = {row["id"] for row in report["open_findings"]}
    assert ids == {row["id"] for row in OPEN_FINDINGS}
    assert "P5-P3T2-LIFECYCLE-OPEN" in ids
