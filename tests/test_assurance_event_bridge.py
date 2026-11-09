from skeleton.kernel.assurance_event_bridge import bind_assurance
from skeleton.kernel.primitives import DomainEvent


def test_bind_assurance_adds_metadata():
    class Envelope:
        state = type("State", (), {"value": "ACCEPTED"})()
        digest = "abc"
        task_id = "task-1"
        source = "test"

    event = DomainEvent(topic="kernel.test", payload={})
    enriched = bind_assurance(event, Envelope())

    assert enriched.payload["assurance"]["digest"] == "abc"
    assert enriched.payload["assurance"]["task_id"] == "task-1"


def test_original_event_is_unchanged():
    event = DomainEvent(topic="kernel.test", payload={})
    class Envelope:
        state = type("State", (), {"value": "PENDING"})()
        digest = "xyz"
        task_id = "task-2"
        source = "test"

    bind_assurance(event, Envelope())
    assert "assurance" not in event.payload
