"""End-to-end offline NPC ending planning through canonical source and replay."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.npc_route_planner import NpcRoutePlanner
from skeleton.game.gameplay.npc_schedule import NpcSchedule, NpcSession, play

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "skeleton/testing/fixtures/lantern_harbor_npc_schedule.json"


def schedule() -> NpcSchedule:
    return NpcSchedule.parse(json.loads(FIXTURE.read_text()))


def test_original_harbor_restoration_is_source_bound_and_replayable() -> None:
    spec = schedule()
    result = NpcRoutePlanner(spec).solve("harbor_restored")
    assert result.status == "solved"
    assert result.session.ending == "harbor_restored"
    assert NpcSession.restore(spec, result.record()["snapshot"]).state_digest == (
        result.record()["state_digest"]
    )
    assert play(spec, result.record()["commands"]).ending == "harbor_restored"


def test_original_alternate_ending_uses_one_interaction() -> None:
    result = NpcRoutePlanner(schedule()).solve("harbor_sealed")
    assert result.status == "solved"
    assert len(result.record()["commands"]) == 1
    assert result.record()["commands"][0]["kind"] == "interact"


def test_route_is_deterministic_with_stable_authored_choices() -> None:
    planner = NpcRoutePlanner(schedule())
    first = planner.solve("harbor_restored")
    second = planner.solve("harbor_restored")
    assert first.record() == second.record()


def test_small_budget_is_explicitly_inconclusive() -> None:
    result = NpcRoutePlanner(schedule()).solve("harbor_restored", max_nodes=1)
    assert result.status == "inconclusive"
    assert result.reason == "node-budget-exhausted"
    assert result.record()["snapshot"] is None


def test_depth_cutoff_is_not_false_impossibility() -> None:
    result = NpcRoutePlanner(schedule()).solve("harbor_restored", max_depth=1)
    assert result.status == "inconclusive"
    assert result.reason == "depth-budget-exhausted"


@pytest.mark.parametrize("kwargs", [
    {"max_nodes": 0}, {"max_nodes": 4097}, {"max_nodes": True},
    {"max_depth": 0}, {"max_depth": 65}, {"player_id": " "},
])
def test_invalid_budgets_and_player_authority_fail_closed(kwargs: dict) -> None:
    with pytest.raises(GameplayContractError):
        NpcRoutePlanner(schedule()).solve("harbor_restored", **kwargs)


def test_unknown_ending_is_rejected() -> None:
    with pytest.raises(GameplayContractError, match="unknown authored ending"):
        NpcRoutePlanner(schedule()).solve("counterfeit_victory")


def test_cli_finds_real_offline_ending_with_replay_snapshot() -> None:
    cmd = [sys.executable, "-m", "scripts.npc_schedule_cli",
           "--schedule", str(FIXTURE), "--solve-ending", "harbor_sealed"]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["status"] == "solved"
    assert NpcSession.restore(schedule(), result["snapshot"]).ending == "harbor_sealed"


def test_cli_rejects_incompatible_solve_and_mutation_options(tmp_path: Path) -> None:
    cmd = [sys.executable, "-m", "scripts.npc_schedule_cli",
           "--schedule", str(FIXTURE), "--solve-ending", "harbor_sealed"]
    for extra in (["--save", str(tmp_path / "save.json")],
                  ["--interactive"], ["--max-search-nodes", "10000000"]):
        run = subprocess.run(cmd + extra, capture_output=True, timeout=20)
        assert run.returncode == 2
    assert not (tmp_path / "save.json").exists()


def test_cli_rejects_duplicate_and_nonfinite_authored_source(tmp_path: Path) -> None:
    from scripts.npc_schedule_cli import main
    for content in (
        '{"schema_version":1,"schema_version":1}',
        '{"schema_version":NaN}',
        '{"schema_version":Infinity}',
    ):
        source = tmp_path / "untrusted.json"
        source.write_text(content)
        assert main(["--schedule", str(source)]) == 2
