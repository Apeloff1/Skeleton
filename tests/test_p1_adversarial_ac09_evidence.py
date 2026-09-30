    candidate = report["candidate"]

    assert report["axis_id"] == AXIS_ID == "AC-09"
    assert report["engine"] == "p1-adversarial-ac09-evidence-v1"
    assert report["batch_id"] == "p1-adversarial-ac09-evidence"
    assert report["candidate_count"] == 1
    assert report["already_bound_count"] == 1
    assert report["candidate_binding_count"] == 0
    assert report["required_evidence_mode_count"] == 4
    assert candidate["binding_present"] is True
    assert tuple(candidate["required_evidence_modes"]) == EXPECTED_MODES
    assert {row["category"] for row in candidate["evidence"]} == set(EXPECTED_MODES)

