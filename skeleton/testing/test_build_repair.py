from skeleton.automation.build_repair import RepairEvidence


def _evidence(**overrides):
    values = {
        "followup_fingerprint": "a" * 64,
        "architecture_fingerprint": "b" * 64,
        "before_fingerprint": "c" * 64,
        "after_fingerprint": "d" * 64,
        "validation_fingerprint": "e" * 64,
        "review_verdict": "accept",
        "review_rounds": 1,
        "model_calls": 2,
        "changed_paths": ("skeleton/example.py",),
    }
    values.update(overrides)
    return RepairEvidence(**values)


def test_repair_evidence_is_deterministic():
    evidence = _evidence()
    assert len(evidence.fingerprint) == 64
    assert evidence.fingerprint == _evidence().fingerprint
    assert evidence.as_dict()["changed_paths"] == ["skeleton/example.py"]


def test_repair_evidence_binds_changed_paths():
    assert _evidence().fingerprint != _evidence(
        changed_paths=("skeleton/other.py",),
    ).fingerprint
