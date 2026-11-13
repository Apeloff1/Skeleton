"""Human choice UX, invalid input fallback and portable checkpoint custody."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.scene_market import import_market
from skeleton.game.gameplay.scene_market_fork import (
    import_market_fork, original_fork, verify_market_fork,
)
from skeleton.game.gameplay.scene_market_fork_interactive import (
    MAX_RETRIES, play_market_fork,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _events(output: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_player_selects_real_winning_market_game():
    report = original_fork()
    before = copy.deepcopy(report)
    output = io.StringIO()
    selected = play_market_fork(
        report, reader=io.StringIO('{"candidate_id":"complete_delivery"}\n'),
        writer=output,
    )
    events = _events(output)
    assert [e["event"] for e in events] == ["fork_board", "selected"]
    assert events[0]["heuristic_candidate"] == "complete_delivery"
    assert events[1]["phase"] == "won"
    assert import_market(events[1]["game_bundle"]) == selected
    assert report == before


def test_rejected_unearned_purchase_then_accepted_route():
    output = io.StringIO()
    selected = play_market_fork(
        original_fork(),
        reader=io.StringIO(
            '{"candidate_id":"unearned_purchase"}\n'
            '{"candidate_id":"complete_delivery"}\n'
        ),
        writer=output,
    )
    events = _events(output)
    assert [e["event"] for e in events] == [
        "fork_board", "rejected", "selected",
    ]
    assert events[1]["remaining_retries"] == MAX_RETRIES - 1
    assert events[1]["checkpoint_state_digest"] == events[0]["checkpoint_state_digest"]
    assert selected["state"]["phase"] == "won"


@pytest.mark.parametrize("bad", [
    '{"candidate_id":"not_authored"}\n',
    '{"candidate_id":"unearned_purchase"}\n',
    '{"candidate_id":42}\n',
    '{"candidate_id":"complete_delivery","bonus":1}\n',
    '{"candidate_id":"x","candidate_id":"complete_delivery"}\n',
    'not-json\n',
])
def test_three_invalid_choices_preserve_portable_preview(bad):
    report = original_fork()
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="retries exhausted"):
        play_market_fork(
            report, reader=io.StringIO(bad * MAX_RETRIES), writer=output,
        )
    events = _events(output)
    assert events[-1]["event"] == "checkpoint"
    assert len([e for e in events if e["event"] == "rejected"]) == MAX_RETRIES
    assert import_market_fork(events[-1]["preview_bundle"]) == report
    assert verify_market_fork(report) == report


def test_eof_and_oversized_input_preserve_preview():
    report = original_fork()
    for value in ("", " " * 4097):
        output = io.StringIO()
        with pytest.raises(SceneTravelError, match="preview preserved"):
            play_market_fork(report, reader=io.StringIO(value), writer=output)
        events = _events(output)
        assert events[-1]["event"] == "checkpoint"
        assert import_market_fork(events[-1]["preview_bundle"]) == report


def test_cli_dispatch_and_checkpoint_on_eof(monkeypatch, capsys):
    from skeleton.__main__ import main
    monkeypatch.setattr("sys.stdin", io.StringIO('{"candidate_id":"complete_delivery"}\n'))
    assert main(["scene-market-fork-play", "demo"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["phase"] == "won"
