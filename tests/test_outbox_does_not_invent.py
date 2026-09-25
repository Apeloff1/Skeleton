"""A missing materialisation is not journaled as zero, and a dead sink stops."""

import pytest

from skeleton.forge.outbox import MaterialiseOutbox


def test_missing_fields_are_not_filled_with_zero() -> None:
    outbox = MaterialiseOutbox()
    with pytest.raises(ValueError):
        outbox.append_materialisation(blueprint_id="", components=1, wires=1, era="now", target="json")
    with pytest.raises(ValueError):
        outbox.append_materialisation(blueprint_id="bp", components=True, wires=1, era="now", target="json")
    assert outbox.journaled_total == 0
    seq = outbox.append_materialisation(blueprint_id="bp", components=2, wires=0, era="now", target="json")
    assert seq == 1
    assert outbox.reconcile() == 1


def test_a_failing_sink_is_dead_lettered_without_its_message() -> None:
    calls = {"n": 0}

    def sink(document):
        calls["n"] += 1
        raise RuntimeError("secret-trace")

    outbox = MaterialiseOutbox(sink)
    outbox.append_materialisation(blueprint_id="bp", components=1, wires=1, era="now", target="json")
    for _ in range(8):
        assert outbox.reconcile() == 0
    assert calls["n"] == 8
    assert outbox.reconcile() == 0
    assert calls["n"] == 8
    intent = outbox.pending()[0]
    assert intent.dead is True
    assert intent.last_error == "RuntimeError"
    assert "secret-trace" not in intent.last_error
