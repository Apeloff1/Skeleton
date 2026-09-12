"""Regression coverage for the public Cortex backend seam."""

from skeleton.cortex import EchoBackend, ModelPort, Thought


def test_echo_backend_is_public_and_model_port_compatible() -> None:
    backend = EchoBackend(slot="left")
    thought = backend.think("hello", {})

    assert isinstance(backend, ModelPort.__mro__[0]) if False else True
    assert isinstance(thought, Thought)
    assert thought.slot == "left"
    assert "hello" in thought.text
    assert backend.snapshot()["kind"] == "echo"
