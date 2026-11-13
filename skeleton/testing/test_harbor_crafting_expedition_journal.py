"""Integrated game -> append-only expedition history -> fork/compare/replay acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_expedition import build_expedition
from skeleton.game.gameplay.harbor_crafting_expedition_journal import (
    append_expedition_journal, compare_expedition_journals,
    create_expedition_journal, expedition_journal_at,
    fast_forward_expedition_journal, fork_expedition_journal,
    verify_expedition_comparison, verify_expedition_journal,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def inputs():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    def board(name):
        return decode((FIXTURES / ("harbor_lantern_quay_" + name + ".json")).read_bytes())
    base = demo_actions()
    actions = base[:16] + [
        {"op": "wait"}, {"op": "talk", "node": "merchant_intro", "choice": "permit"},
    ] + base[16:]
    return source, board("survey"), board("weather"), board("dialogue"), actions


def report(count):
    source, survey, weather, dialogue, actions = inputs()
    return build_expedition(source, survey, weather, dialogue, actions[:count])


def test_real_save_history_replay_and_historical_checkpoint():
    first, second, final = report(7), report(17), report(20)
    root = create_expedition_journal(first)
    advanced = append_expedition_journal(root, second, expected_digest=root["journal_digest"])
    complete = append_expedition_journal(advanced, final,
                                         expected_digest=advanced["journal_digest"])
    assert verify_expedition_journal(decode(canonical(complete)))["complete"]
    assert expedition_journal_at(complete, 0) == first
    assert expedition_journal_at(complete, 1) == second
    assert expedition_journal_at(complete, 2) == final
    assert complete["entries"][-1]["previous"] == complete["entries"][-2]["digest"]


def test_stale_lease_repeated_or_divergent_history_denied():
    first, second = report(7), report(17)
    root = create_expedition_journal(first)
    with pytest.raises(HarborError, match="stale"):
        append_expedition_journal(root, second, expected_digest="0"*64)
    with pytest.raises(HarborError, match="divergence"):
        append_expedition_journal(root, first, expected_digest=root["journal_digest"])
    source, survey, weather, dialogue, actions = inputs()
    alternate = build_expedition(source, survey, weather, dialogue,
                                 actions[:7] + [{"op": "wait"}])
    extended = append_expedition_journal(root, second, expected_digest=root["journal_digest"])
    with pytest.raises(HarborError, match="divergence"):
        append_expedition_journal(extended, alternate,
                                  expected_digest=extended["journal_digest"])


def test_safe_fork_compare_fast_forward_and_divergence():
    first, second, final = report(7), report(17), report(20)
    root = create_expedition_journal(first)
    middle = append_expedition_journal(root, second, expected_digest=root["journal_digest"])
    complete = append_expedition_journal(middle, final,
                                         expected_digest=middle["journal_digest"])
    fork = fork_expedition_journal(complete, 0,
                                   expected_digest=complete["journal_digest"])
    assert fork == root
    comparison = compare_expedition_journals(fork, complete)
    assert verify_expedition_comparison(comparison)["relation"] == "right_ahead"
    assert fast_forward_expedition_journal(
        fork, complete, expected_digest=fork["journal_digest"]) == complete
    with pytest.raises(HarborError, match="strict ancestry"):
        fast_forward_expedition_journal(
            complete, fork, expected_digest=complete["journal_digest"])
    source, survey, weather, dialogue, actions = inputs()
    alternate = build_expedition(source, survey, weather, dialogue,
                                 actions[:7] + [{"op": "wait"}])
    other = append_expedition_journal(root, alternate,
                                      expected_digest=root["journal_digest"])
    assert compare_expedition_journals(other, complete)["relation"] == "diverged"


def test_resealed_history_and_comparison_forgery_fail_closed():
    root = create_expedition_journal(report(7))
    advanced = append_expedition_journal(root, report(17),
                                         expected_digest=root["journal_digest"])
    forged = deepcopy(advanced)
    forged["entries"][1]["previous"] = "0"*64
    forged["entries"][1]["digest"] = digest({
        k: v for k, v in forged["entries"][1].items() if k != "digest"
    })
    forged["journal_digest"] = digest({
        k: v for k, v in forged.items() if k != "journal_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_expedition_journal(forged)
    comparison = compare_expedition_journals(root, advanced)
    comparison["relation"] = "identical"
    comparison["comparison_digest"] = digest({
        k: v for k, v in comparison.items() if k != "comparison_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_expedition_comparison(comparison)


def test_cli_journal_save_replay_fork_and_fast_forward(tmp_path):
    first, second, final = report(7), report(17), report(20)
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        process = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert process.returncode == 0, process.stderr.decode()
        return decode(process.stdout)

    first_path = write("first", first)
    root = call("expedition-journal-init", "--expedition", first_path)
    root_path = write("root", root)
    second_path = write("second", second)
    middle = call("expedition-journal-append", "--expedition-journal", root_path,
                  "--expedition", second_path,
                  "--expected-expedition-journal-digest", root["journal_digest"])
    middle_path = write("middle", middle)
    final_path = write("final", final)
    complete = call("expedition-journal-append", "--expedition-journal", middle_path,
                    "--expedition", final_path,
                    "--expected-expedition-journal-digest", middle["journal_digest"])
    complete_path = write("complete", complete)
    assert call("expedition-journal-verify", "--expedition-journal", complete_path)["complete"]
    assert call("expedition-journal-at", "--expedition-journal", complete_path,
                "--revision-index", "1") == second
    comparison = call("expedition-journal-compare", "--expedition-journal", root_path,
                      "--other-expedition-journal", complete_path)
    comparison_path = write("comparison", comparison)
    assert call("expedition-journal-verify-comparison",
                "--expedition-comparison", comparison_path)["relation"] == "right_ahead"
    assert call("expedition-journal-fast-forward", "--expedition-journal", root_path,
                "--other-expedition-journal", complete_path,
                "--expected-expedition-journal-digest", root["journal_digest"]) == complete
