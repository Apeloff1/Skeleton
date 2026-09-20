from skeleton.kernel.event_assurance_adapter import EventAssuranceAdapter


def test_missing_identity_is_rejected():
    adapter = EventAssuranceAdapter()
    result = adapter.validate(type("Envelope", (), {"task_id": "", "digest": "x", "state": None})())
    assert result.accepted is False


def test_metadata_attachment():
    adapter = EventAssuranceAdapter()
    envelope = type("Envelope", (), {"task_id": "task-1", "digest": "abc", "state": type("State", (), {"value": "pending"})()})()
    payload = adapter.attach_metadata({}, envelope)
    assert payload["assurance"]["digest"] == "abc"
