"""Diet time-boxed franchise — port of gameforge-rs voting.rs.

Also locks the legacy Voting.elect API so the Diet add stays extend-only.
"""

from __future__ import annotations

import pytest

from skeleton.agents.voting import (
    DEFAULT_OPEN_SECS,
    MIN_OPEN_SECS,
    Ballot,
    Diet,
    DietBallot,
    Measure,
    VoteMethod,
    Voting,
    VotingError,
)


class Clock:
    """Injectable monotonic-enough wall for Diet time-box tests."""

    def __init__(self, t: float = 1_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, secs: float) -> None:
        self.t += secs


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def diet(clock: Clock) -> Diet:
    n = {"i": 0}

    def ids() -> str:
        n["i"] += 1
        return f"m-{n['i']}"

    return Diet(clock=clock, id_factory=ids)


# ---------------------------------------------------------------------------
# Legacy elect API — must stay byte-stable for existing callers
# ---------------------------------------------------------------------------


def test_elect_plurality_unchanged():
    v = Voting()
    winner, n = v.elect(
        ["alpha", "beta"],
        [
            Ballot("a", ("alpha",)),
            Ballot("b", ("alpha",)),
            Ballot("c", ("beta",)),
        ],
        method=VoteMethod.PLURALITY,
    )
    assert winner == "alpha"
    assert n == 3


def test_elect_approval_unchanged():
    v = Voting()
    winner, n = v.elect(
        ["x", "y", "z"],
        [
            Ballot("a", ("x", "y")),
            Ballot("b", ("y", "z")),
            Ballot("c", ("y",)),
        ],
        method=VoteMethod.APPROVAL,
    )
    assert winner == "y"
    assert n == 3


def test_elect_ranked_default_unchanged():
    v = Voting()
    winner, n = v.elect(
        ["red", "blue", "green"],
        [
            Ballot("a", ("green", "blue", "red")),
            Ballot("b", ("green", "red")),
            Ballot("c", ("blue", "red")),
            Ballot("d", ("red",)),
        ],
    )
    assert winner == "green"
    assert n == 4


def test_elect_ranked_no_options_raises():
    with pytest.raises(VotingError, match="no options"):
        Voting().elect([], [])


# ---------------------------------------------------------------------------
# Diet propose / cast / tally / close
# ---------------------------------------------------------------------------


def test_propose_requires_two_options(diet: Diet):
    with pytest.raises(VotingError, match="at least two options"):
        diet.propose("solo", ["only"], "chair")
    with pytest.raises(VotingError, match="at least two options"):
        diet.propose("empty", [], "chair")


def test_propose_clamps_open_window_to_min(diet: Diet, clock: Clock):
    m = diet.propose("short", ["stay", "go"], "chair", open_secs=1)
    assert isinstance(m, Measure)
    assert m.id == "m-1"
    assert m.options[0] == "stay"
    assert m.opened == clock.t
    assert m.closes == clock.t + MIN_OPEN_SECS
    assert m.closed is False
    assert m.closes - m.opened == MIN_OPEN_SECS


def test_propose_default_window_is_a_day(diet: Diet, clock: Clock):
    m = diet.propose("day", ["aye", "nay"], "chair")
    assert m.closes == clock.t + DEFAULT_OPEN_SECS


def test_cast_and_plurality_tally(diet: Diet):
    m = diet.propose("fleet", ["hold", "sail", "retreat"], "admiral", open_secs=120)
    b1 = diet.cast(m.id, "alice", "sail")
    b2 = diet.cast(m.id, "bob", "sail")
    diet.cast(m.id, "cara", "hold")
    assert isinstance(b1, DietBallot)
    assert b1.voter == "alice"
    assert b1.option == "sail"
    assert b2.cast_at >= b1.cast_at
    t = diet.tally(m.id)
    assert t["measure"] == "fleet"
    assert t["closed"] is False
    assert t["ballots"] == 3
    assert t["counts"] == {"hold": 1, "sail": 2, "retreat": 0}
    assert t["leading"] == "sail"
    roll = diet.roll(m.id)
    assert [b.voter for b in roll] == ["alice", "bob", "cara"]


def test_tally_tie_breaks_to_status_quo(diet: Diet):
    m = diet.propose("keep?", ["status-quo", "reform"], "chair", open_secs=120)
    diet.cast(m.id, "alice", "reform")
    diet.cast(m.id, "bob", "status-quo")
    t = diet.tally(m.id)
    assert t["counts"] == {"status-quo": 1, "reform": 1}
    assert t["leading"] == "status-quo"


def test_tally_empty_roll_leads_status_quo(diet: Diet):
    m = diet.propose("idle", ["keep", "change"], "chair", open_secs=120)
    t = diet.tally(m.id)
    assert t["ballots"] == 0
    assert t["counts"] == {"keep": 0, "change": 0}
    assert t["leading"] == "keep"
    assert t["closed"] is False


def test_one_voice_per_measure(diet: Diet):
    m = diet.propose("once", ["aye", "nay"], "chair", open_secs=120)
    diet.cast(m.id, "alice", "aye")
    with pytest.raises(VotingError, match="already spoken"):
        diet.cast(m.id, "alice", "nay")
    assert diet.tally(m.id)["ballots"] == 1
    assert diet.tally(m.id)["counts"]["aye"] == 1


def test_unknown_option_and_measure(diet: Diet):
    m = diet.propose("opts", ["aye", "nay"], "chair", open_secs=120)
    with pytest.raises(VotingError, match="no such option"):
        diet.cast(m.id, "alice", "maybe")
    with pytest.raises(VotingError, match="no such measure"):
        diet.cast("ghost", "alice", "aye")
    with pytest.raises(VotingError, match="no such measure"):
        diet.tally("ghost")
    with pytest.raises(VotingError, match="no such measure"):
        diet.close("ghost")


def test_explicit_close_refuses_further_ballots(diet: Diet):
    m = diet.propose("seal", ["aye", "nay"], "chair", open_secs=600)
    diet.cast(m.id, "alice", "aye")
    sealed = diet.close(m.id)
    assert sealed.closed is True
    with pytest.raises(VotingError, match="the measure is closed"):
        diet.cast(m.id, "bob", "nay")
    t = diet.tally(m.id)
    assert t["closed"] is True
    assert t["ballots"] == 1
    assert t["leading"] == "aye"


# ---------------------------------------------------------------------------
# Time-box — the Diet franchise
# ---------------------------------------------------------------------------


def test_time_box_refuses_cast_after_close_instant(diet: Diet, clock: Clock):
    m = diet.propose("sunset", ["aye", "nay"], "chair", open_secs=60)
    diet.cast(m.id, "alice", "aye")
    # RS: closed when now > closes (equality still open)
    clock.t = m.closes
    diet.cast(m.id, "bob", "nay")
    clock.advance(0.001)
    with pytest.raises(VotingError, match="the measure is closed"):
        diet.cast(m.id, "cara", "aye")
    t = diet.tally(m.id)
    assert t["closed"] is True
    assert t["ballots"] == 2
    assert t["counts"] == {"aye": 1, "nay": 1}
    assert t["leading"] == "aye"  # tie → status quo


def test_time_box_tally_closes_without_explicit_close(diet: Diet, clock: Clock):
    m = diet.propose("expire", ["keep", "drop"], "chair", open_secs=60)
    assert diet.tally(m.id)["closed"] is False
    clock.advance(MIN_OPEN_SECS)
    assert diet.tally(m.id)["closed"] is False  # now == closes
    clock.advance(1)
    t = diet.tally(m.id)
    assert t["closed"] is True
    with pytest.raises(VotingError, match="the measure is closed"):
        diet.cast(m.id, "late", "drop")


def test_time_box_min_window_survives_zero_open_secs(diet: Diet, clock: Clock):
    m = diet.propose("floor", ["a", "b"], "chair", open_secs=0)
    clock.advance(MIN_OPEN_SECS - 1)
    diet.cast(m.id, "early", "a")
    clock.advance(2)
    with pytest.raises(VotingError, match="the measure is closed"):
        diet.cast(m.id, "late", "b")


def test_measures_lists_open_and_closed(diet: Diet, clock: Clock):
    a = diet.propose("one", ["x", "y"], "chair", open_secs=60)
    b = diet.propose("two", ["p", "q"], "chair", open_secs=60)
    diet.close(a.id)
    clock.advance(MIN_OPEN_SECS + 1)
    listed = diet.measures()
    assert {m.id for m in listed} == {a.id, b.id}
    assert diet.tally(a.id)["closed"] is True
    assert diet.tally(b.id)["closed"] is True
