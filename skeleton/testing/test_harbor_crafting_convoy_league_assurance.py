"""Replay assurance, journal ancestry, leaderboard and original-game acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league import build_league
from skeleton.game.gameplay.harbor_crafting_convoy_league_solver import (
    solve_league, verify_league_plan,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_package import build_league_package
from skeleton.game.gameplay.harbor_crafting_convoy_league_journal import (
    append_league_journal, compare_league_journals, create_league_journal,
    fast_forward_league_journal, league_journal_at, verify_league_journal,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_board import (
    build_league_leaderboard, verify_league_leaderboard,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_acceptance import (
    accept_league, verify_league_acceptance,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def source_league():
    return (
        load_source(FIXTURES / "harbor_lantern_quay.json"),
        decode((FIXTURES / "harbor_lantern_quay_convoy_league.json").read_bytes()),
    )


def test_solver_earns_both_rounds_and_replay():
    source, league = source_league()
    plan = solve_league(source, league)
    assert plan["save"]["complete"]
    assert verify_league_plan(decode(canonical(plan)))["complete"]
    assert len(plan["plans"]) == 2
    assert plan["save"]["score"] >= league["target_score"]


def test_journal_history_fast_forward_and_divergence():
    source, league = source_league()
    plan = solve_league(source, league)
    package = build_league_package("championship", source, league)
    journal = create_league_journal(package)
    first = plan["plans"][0]["actions"]
    second = plan["plans"][1]["actions"]
    partial = append_league_journal(journal, first[:12],
        expected_digest=journal["journal_digest"])
    next_ = append_league_journal(partial, first[12:],
        expected_digest=partial["journal_digest"])
    full = append_league_journal(next_, second,
        expected_digest=next_["journal_digest"])
    assert verify_league_journal(full)["complete"]
    assert league_journal_at(full, 2) == next_
    assert compare_league_journals(partial, full)["fast_forward"]
    assert fast_forward_league_journal(partial, full,
        expected_digest=partial["journal_digest"]) == full
    with pytest.raises(HarborError, match="stale"):
        fast_forward_league_journal(partial, full, expected_digest="0" * 64)
    with pytest.raises(HarborError, match="terminal"):
        append_league_journal(full, [{"op": "wait"}],
            expected_digest=full["journal_digest"])
    forged = deepcopy(full)
    forged["entries"][0]["actions"][0] = {"op": "wait"}
    forged["entries"][0]["digest"] = digest({
        k: v for k, v in forged["entries"][0].items() if k != "digest"
    })
    forged["journal_digest"] = digest({
        k: v for k, v in forged.items() if k != "journal_digest"
    })
    with pytest.raises(HarborError):
        verify_league_journal(forged)


def test_board_ranking_and_resealed_tampering():
    source, league = source_league()
    plan = solve_league(source, league)
    save = plan["save"]
    board = build_league_leaderboard([
        {"id": "captain_ada", "save": save},
        {"id": "captain_bea", "save": deepcopy(save)},
    ])
    ranking = verify_league_leaderboard(board)["ranking"]
    assert [row["id"] for row in ranking] == ["captain_ada", "captain_bea"]
    bad = deepcopy(board)
    bad["ranking"][0]["score"] = 999
    bad["board_digest"] = digest({k: v for k, v in bad.items() if k != "board_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_league_leaderboard(bad)
    with pytest.raises(HarborError, match="duplicate"):
        build_league_leaderboard([{"id": "same", "save": save}] * 2)


def test_one_command_acceptance_replays_all_layers():
    source, league = source_league()
    receipt = accept_league(source, league)
    status = verify_league_acceptance(decode(canonical(receipt)))
    assert status["verified"] and status["complete"]
    assert status["score"] >= league["target_score"]
    forged = deepcopy(receipt)
    forged["summary"]["score"] += 1
    forged["acceptance_digest"] = digest({
        k: v for k, v in forged.items() if k != "acceptance_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_league_acceptance(forged)


def test_cli_solver_acceptance_journal_and_leaderboard(tmp_path):
    source, league = source_league()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)
    league_file = str(FIXTURES / "harbor_lantern_quay_convoy_league.json")
    plan = call("league-solve", "--league-board", league_file)
    assert call("league-verify-plan", "--league-plan", write("plan", plan))["complete"]
    receipt = call("league-accept", "--league-board", league_file)
    assert call("league-verify-accept", "--league-acceptance",
                write("receipt", receipt))["complete"]
    package = call("league-package-build", "--league-board", league_file)
    journal = call("league-journal-init", "--league-package", write("package", package))
    first = plan["plans"][0]["actions"]
    journal = call("league-journal-append", "--league-journal", write("journal", journal),
        "--actions", write("actions", first),
        "--expected-league-journal-digest", journal["journal_digest"])
    assert call("league-journal-verify", "--league-journal",
                write("journal2", journal))["entries"] == 1
    board = call("league-board", "--entrants", write("entrants", [
        {"id": "player", "save": plan["save"]}
    ]))
    assert call("league-board-verify", "--league-board-report",
                write("board", board))["ranking"][0]["score"] == plan["save"]["score"]
