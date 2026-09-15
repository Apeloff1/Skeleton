"""Focused regressions for the converged Jeeves session hardening."""

import pytest

from skeleton.jeeves import Jeeves, SessionMode
from skeleton.kernel.errors import SessionError


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
