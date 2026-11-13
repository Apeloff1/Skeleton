"""Checkpoint, optimistic continuation and branching replay acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle,
    load_source, verify_bundle,
)
from skeleton.game.gameplay.harbor_crafting_sessions import (
    branch_portfolio, checkpoint, resume_bundle, state_at, verify_portfolio,
)

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def world():
    return load_source(WORLD)


def checkpoint_before_choice():
    return export_bundle(world(), demo_actions()[:-1])


def test_resume_exact_checkpoint_is_byte_identical_to_uninterrupted_game():
    actions = demo_actions()
    full = export_bundle(world(), actions, require_win=True)
    for cut in (0, 1, 7, 12, 16, 17):
        prefix = export_bundle(world(), actions[:cut])
        resumed = resume_bundle(
            prefix, actions[cut:],
            expected_terminal_digest=prefix["terminal_digest"],
            require_win=True,
        )
        assert canonical(resumed) == canonical(full)
        assert verify_bundle(resumed, require_win=True)["ending"] == "beacon"


def test_historical_seek_replays_state_and_keeps_original_save_immutable():
    full = export_bundle(world(), demo_actions())
    original = deepcopy(full)
    for tick in (0, 2, 7, 12, len(demo_actions())):
        partial = checkpoint(full, tick)
        assert len(partial["events"]) == tick
        assert state_at(full, tick) == partial["state"]
        assert partial == export_bundle(world(), demo_actions()[:tick])
    assert full == original


def test_checkpoint_refuses_boolean_negative_future_and_tampered_input():
    full = export_bundle(world(), demo_actions())
    for tick in (-1, True, len(demo_actions()) + 1, "3"):
        with pytest.raises(HarborError):
            checkpoint(full, tick)
    full["events"][0]["after"] = "0" * 64
    with pytest.raises(HarborError):
        checkpoint(full, 0)


def test_cas_rejects_stale_or_missing_terminal_digest():
    prefix = export_bundle(world(), demo_actions()[:8])
    for wrong in ("", "0" * 64, None):
        with pytest.raises(HarborError, match="stale checkpoint"):
            resume_bundle(prefix, demo_actions()[8:], expected_terminal_digest=wrong)
    assert prefix["state"]["ending"] is None


def test_resume_rejects_illegal_actions_without_mutating_verified_prefix():
    prefix = export_bundle(world(), demo_actions()[:2])
    original = deepcopy(prefix)
    with pytest.raises(HarborError):
        resume_bundle(prefix, [{"op": "move", "direction": "north"}], expected_terminal_digest=prefix["terminal_digest"])
    assert prefix == original


def test_resume_cannot_append_after_ending_or_exceed_tick_budget():
    complete = export_bundle(world(), demo_actions())
    with pytest.raises(HarborError, match="already complete"):
        resume_bundle(complete, [{"op": "wait"}], expected_terminal_digest=complete["terminal_digest"])
    partial = export_bundle(world(), [])
    with pytest.raises(HarborError, match="remaining tick budget"):
        resume_bundle(partial, [{"op": "wait"}] * 257, expected_terminal_digest=partial["terminal_digest"])


def test_branch_portfolio_verifies_two_real_choice_consequences():
    prefix = checkpoint_before_choice()
    branches = {
        "beacon": [{"op": "choose", "choice": "signal"}],
        "shelter": [{"op": "choose", "choice": "shelter"}],
    }
    portfolio = branch_portfolio(prefix, branches)
    assert verify_portfolio(decode(canonical(portfolio))) == {
        "beacon": "beacon", "shelter": "safe_harbor",
    }
    assert portfolio["entries"][0]["bundle"]["terminal_digest"] != portfolio["entries"][1]["bundle"]["terminal_digest"]
    assert prefix["state"]["ending"] is None


@pytest.mark.parametrize("mutation", [
    lambda p: p["entries"][0]["bundle"]["state"].update({"ending": "forged"}),
    lambda p: p["entries"][0]["actions"][0].update({"choice": "shelter"}),
    lambda p: p["entries"][0].update({"terminal_digest": "0" * 64}),
    lambda p: p.update({"root_digest": "0" * 64}),
    lambda p: p["root"]["events"][0].update({"sequence": 55}),
])
def test_portfolio_rejects_modified_root_branch_and_terminal(mutation):
    portfolio = branch_portfolio(checkpoint_before_choice(), {
        "beacon": [{"op": "choose", "choice": "signal"}],
    })
    mutation(portfolio)
    portfolio["portfolio_digest"] = digest({k: v for k, v in portfolio.items() if k != "portfolio_digest"})
    with pytest.raises(HarborError):
        verify_portfolio(portfolio)


def test_portfolio_rejects_duplicate_or_invalid_names_and_excess_branches():
    prefix = checkpoint_before_choice()
    with pytest.raises(HarborError):
        branch_portfolio(prefix, {"bad name": []})
    with pytest.raises(HarborError):
        branch_portfolio(prefix, {str(i): [] for i in range(5)})
    with pytest.raises(HarborError):
        branch_portfolio(export_bundle(world(), demo_actions()), {"again": []})


def test_portfolio_rejects_reordered_branches_even_with_resealed_outer_digest():
    portfolio = branch_portfolio(checkpoint_before_choice(), {
        "a": [{"op": "choose", "choice": "signal"}],
        "b": [{"op": "choose", "choice": "shelter"}],
    })
    portfolio["entries"].reverse()
    portfolio["portfolio_digest"] = digest({k: v for k, v in portfolio.items() if k != "portfolio_digest"})
    with pytest.raises(HarborError, match="ordering"):
        verify_portfolio(portfolio)


def test_cli_checkpoint_resume_and_portfolio_end_to_end(tmp_path):
    command = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    full = export_bundle(world(), demo_actions(), require_win=True)
    full_path = tmp_path / "full.json"
    full_path.write_bytes(canonical(full))
    partial = subprocess.run(
        command + ["checkpoint", "--bundle", str(full_path), "--tick", "17"],
        capture_output=True, check=False,
    )
    assert partial.returncode == 0, partial.stderr.decode()
    prefix = decode(partial.stdout)
    assert prefix["state"]["delivered"] is True
    prefix_path = tmp_path / "prefix.json"
    prefix_path.write_bytes(partial.stdout)
    continuation = tmp_path / "continuation.json"
    continuation.write_bytes(canonical([{"op": "choose", "choice": "signal"}]))
    resumed = subprocess.run(
        command + [
            "resume", "--bundle", str(prefix_path), "--actions", str(continuation),
            "--expected-terminal-digest", prefix["terminal_digest"], "--require-win",
        ],
        capture_output=True, check=False,
    )
    assert resumed.returncode == 0, resumed.stderr.decode()
    assert decode(resumed.stdout) == full
    branches = tmp_path / "branches.json"
    branches.write_bytes(canonical({
        "beacon": [{"op": "choose", "choice": "signal"}],
        "shelter": [{"op": "choose", "choice": "shelter"}],
    }))
    produced = subprocess.run(
        command + ["portfolio", "--bundle", str(prefix_path), "--branches", str(branches)],
        capture_output=True, check=False,
    )
    assert produced.returncode == 0, produced.stderr.decode()
    portfolio_path = tmp_path / "portfolio.json"
    portfolio_path.write_bytes(produced.stdout)
    checked = subprocess.run(
        command + ["verify-portfolio", "--bundle", str(portfolio_path)],
        capture_output=True, check=False,
    )
    assert checked.returncode == 0, checked.stderr.decode()
    assert decode(checked.stdout)["branches"]["shelter"] == "safe_harbor"


def test_cli_resume_refuses_wrong_lease_and_emits_no_fake_save(tmp_path):
    prefix = checkpoint_before_choice()
    saved = tmp_path / "save.json"
    saved.write_bytes(canonical(prefix))
    actions = tmp_path / "actions.json"
    actions.write_bytes(canonical([{"op": "choose", "choice": "signal"}]))
    command = [sys.executable, "-m", "scripts.game.harbor_crafting", "resume",
               "--bundle", str(saved), "--actions", str(actions),
               "--expected-terminal-digest", "0" * 64]
    failed = subprocess.run(command, capture_output=True, check=False)
    assert failed.returncode == 2
    assert failed.stdout == b""
