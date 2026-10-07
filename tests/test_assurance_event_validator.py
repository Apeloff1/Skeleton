from skeleton.kernel.assurance_event_validator import AssuranceEventValidator


class DummyEnvelope:
    def __init__(self, task_id, digest, state, source="test"):
        self.task_id = task_id
        self.digest = digest
        self.state = state
        self.source = source


class TestState:
    ACCEPTED = "ACCEPTED"


def test_missing_identity_rejected():
    result = AssuranceEventValidator().validate_payload({"assurance_digest": "abc"})
    assert not result.valid


def test_digest_required():
    result = AssuranceEventValidator().validate_payload({"task_id": "task"})
    assert not result.valid


def test_valid_payload():
    result = AssuranceEventValidator().validate_payload(
        {"task_id": "task", "assurance_digest": "abc"}
    )
    assert result.valid
