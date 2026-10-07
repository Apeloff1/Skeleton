"""Adversarial resilience tests for the public Jeeves session engine."""

import pytest

from skeleton.jeeves import Jeeves, SessionMode
from skeleton.kernel.errors import SessionError


def test_responder_failure_rolls_back_learner_turn():
    def fail(_message, _history, _context):
        raise RuntimeError("backend exploded")

    jeeves = Jeeves(responder=fail)
    session = jeeves.open_session("u")

    with pytest.raises(RuntimeError, match="backend exploded"):
        jeeves.ask(session.session_id, "hello")

    assert session.turns == []


def test_system_exit_from_responder_also_rolls_back_learner_turn():
    def stop(_message, _history, _context):
        raise SystemExit(0)

    jeeves = Jeeves(responder=stop)
    session = jeeves.open_session("u")

    with pytest.raises(SystemExit):
        jeeves.ask(session.session_id, "hello")

    assert session.turns == []


@pytest.mark.parametrize("reply", [None, "", "   ", 123])
def test_invalid_responder_reply_rolls_back_turn(reply):
    jeeves = Jeeves(responder=lambda *_args: reply)
    session = jeeves.open_session("u")

    with pytest.raises(SessionError, match="invalid reply"):
        jeeves.ask(session.session_id, "hello")

    assert session.turns == []


def test_responder_receives_only_committed_prior_history():
    seen = []

    def responder(message, history, _context):
        seen.append((message, [turn.content for turn in history]))
        return "ok"

    jeeves = Jeeves(responder=responder)
    session = jeeves.open_session("u")
    jeeves.ask(session.session_id, "first")
    jeeves.ask(session.session_id, "second")

    assert seen[0] == ("first", [])
    assert seen[1] == ("second", ["first", "ok"])


def test_responder_cannot_mutate_committed_history_through_snapshot():
    def responder(_message, history, _context):
        if history:
            history[0].content = "poisoned"
        return "ok"

    jeeves = Jeeves(responder=responder)
    session = jeeves.open_session("u")
    jeeves.ask(session.session_id, "first")
    jeeves.ask(session.session_id, "second")

    assert session.turns[0].content == "first"
    assert [turn.content for turn in session.turns] == ["first", "ok", "second", "ok"]


def test_turn_budget_reserves_space_for_complete_exchange():
    jeeves = Jeeves(max_turns=2)
    session = jeeves.open_session("u")

    jeeves.ask(session.session_id, "first")
    with pytest.raises(SessionError, match="turn limit"):
        jeeves.ask(session.session_id, "second")

    assert len(session.turns) == 2


def test_oversized_message_is_rejected_before_mutation():
    jeeves = Jeeves(max_message_chars=5)
    session = jeeves.open_session("u")

    with pytest.raises(SessionError, match="size limit"):
        jeeves.ask(session.session_id, "123456")

    assert session.turns == []


def test_non_mapping_context_is_rejected_before_mutation():
    jeeves = Jeeves()
    session = jeeves.open_session("u")

    with pytest.raises(SessionError, match="context"):
        jeeves.ask(session.session_id, "hello", context="bad")  # type: ignore[arg-type]

    assert session.turns == []


def test_session_capacity_fails_closed_while_all_sessions_active():
    jeeves = Jeeves(max_sessions=1)
    first = jeeves.open_session("u1")

    with pytest.raises(SessionError, match="capacity"):
        jeeves.open_session("u2")

    assert jeeves.get_session(first.session_id).is_open


def test_closed_session_is_reclaimed_at_capacity():
    jeeves = Jeeves(max_sessions=1)
    old = jeeves.open_session("u1")
    jeeves.close_session(old.session_id)

    fresh = jeeves.open_session("u2")

    assert fresh.is_open
    with pytest.raises(SessionError, match="unknown session"):
        jeeves.get_session(old.session_id)


def test_invalid_open_mode_is_rejected_before_closed_session_reclaim():
    jeeves = Jeeves(max_sessions=1)
    old = jeeves.open_session("u1")
    jeeves.close_session(old.session_id)

    with pytest.raises(SessionError, match="mode"):
        jeeves.open_session("u2", mode="not-a-mode")  # type: ignore[arg-type]

    assert jeeves.get_session(old.session_id) is old


def test_invalid_mode_change_does_not_mutate_session():
    jeeves = Jeeves()
    session = jeeves.open_session("u")

    with pytest.raises(SessionError, match="mode"):
        jeeves.set_mode(session.session_id, "not-a-mode")  # type: ignore[arg-type]

    assert session.mode is SessionMode.TUTORING


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_turns": 1},
        {"max_turns": 0},
        {"max_turns": True},
        {"max_sessions": 0},
        {"max_sessions": True},
        {"max_message_chars": 0},
        {"max_message_chars": True},
    ],
)
def test_invalid_resource_limits_fail_fast(kwargs):
    with pytest.raises(ValueError):
        Jeeves(**kwargs)


def test_non_callable_responder_fails_fast():
    with pytest.raises(TypeError, match="callable"):
        Jeeves(responder="not callable")  # type: ignore[arg-type]
