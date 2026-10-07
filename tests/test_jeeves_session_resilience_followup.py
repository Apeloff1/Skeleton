"""Adversarial follow-ups for Jeeves session transaction invariants."""

import pytest

from skeleton.jeeves import Jeeves


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_turns": True},
        {"max_turns": False},
        {"max_sessions": True},
        {"max_sessions": False},
        {"max_message_chars": True},
        {"max_message_chars": False},
    ],
)
def test_boolean_resource_limits_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Jeeves(**kwargs)


def test_baseexception_responder_failure_rolls_back_learner_turn():
    def stop(_message, _history, _context):
        raise SystemExit("stop")

    jeeves = Jeeves(responder=stop)
    session = jeeves.open_session("u")

    with pytest.raises(SystemExit, match="stop"):
        jeeves.ask(session.session_id, "hello")

    assert session.turns == []
