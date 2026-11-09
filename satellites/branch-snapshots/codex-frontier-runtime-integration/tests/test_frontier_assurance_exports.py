def test_assurance_exports_are_importable():
    from skeleton.frontier import assurance

    assert assurance.BoundedInt
    assert assurance.Decision
    assert assurance.Outcome
    assert assurance.Provenance
    assert assurance.QualityGate
    assert assurance.Snapshot
    assert assurance.Verification
    assert assurance.state_digest
