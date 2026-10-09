from skeleton.p5.review import run_review


def test_review_holds_probes_and_has_no_open_findings() -> None:
    report = run_review()
    assert report["probes_held"] == 4
    assert report["open_findings"] == []
    assert report["clean"] is True
    assert report["stored_prose"] == 0
