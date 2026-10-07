"""Regression coverage for the public Cortex backend seam."""

from skeleton.cortex import EchoBackend, Thought


def test_echo_backend_is_public_and_usable() -> None:
    backend = EchoBackend(slot="left")
    thought = backend.think("hello", {})

    assert isinstance(thought, Thought)
    assert thought.slot == "left"
    assert "hello" in thought.text
    assert backend.snapshot()["kind"] == "echo"
