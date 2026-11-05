"""Real authored quest choice planning, replay and installed CLI."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.quest_route_planner import QuestRoutePlanner
from skeleton.game.gameplay.quest_session import (
    GameplayContractError, QuestEngine, QuestPlan, QuestReward, QuestSpec,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/game/fixtures/lantern_harbor_quests.json"


def engine() -> QuestEngine:
    return QuestEngine(QuestPlan.from_record(json.loads(FIXTURE.read_text())))


def test_source_bound_original_ending_route_replays_and_restores() -> None:
    canonical = engine()
    route = QuestRoutePlanner(canonical).solve("safe_harbor")
    assert route.status == "solved"
    assert route.session.ending_id == "safe_harbor"
    assert canonical.replay(route.session.events) == route.session
    assert canonical.restore(route.record()["save"]) == route.session
    assert route.record()["state_digest"] == route.session.state_digest


def test_identical_authored_quests_produce_identical_witness() -> None:
    planner = QuestRoutePlanner(engine())
    assert planner.solve("safe_harbor").record() == (
        planner.solve("safe_harbor").record()
    )


def test_bounded_search_reports_inconclusive_instead_of_unreachable() -> None:
    planner = QuestRoutePlanner(engine())
    assert planner.solve("safe_harbor", max_nodes=1).status == "inconclusive"
    result = planner.solve("safe_harbor", max_depth=1)
    assert result.status == "inconclusive"
    assert result.reason == "depth-budget-exhausted"


@pytest.mark.parametrize("kwargs", [
    {"max_nodes": 0}, {"max_nodes": True}, {"max_nodes": 4097},
    {"max_depth": 0}, {"max_depth": 65},
])
def test_invalid_route_limits_fail_closed(kwargs: dict) -> None:
    with pytest.raises(GameplayContractError):
        QuestRoutePlanner(engine()).solve("safe_harbor", **kwargs)


def test_nonexistent_ending_rejected() -> None:
    with pytest.raises(GameplayContractError, match="unknown authored"):
        QuestRoutePlanner(engine()).solve("counterfeit", max_nodes=32)


def test_installed_quest_cli_solves_original_ending() -> None:
    cmd = [sys.executable, "-m", "skeleton", "quest", "solve",
           "--plan", str(FIXTURE), "--goal-ending", "safe_harbor"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "solved"
    assert engine().restore(payload["save"]).ending_id == "safe_harbor"


def test_cli_rejects_unsafe_route_options_and_does_not_write(tmp_path: Path) -> None:
    cmd = [sys.executable, "-m", "skeleton", "quest", "solve",
           "--plan", str(FIXTURE), "--goal-ending", "safe_harbor"]
    target = tmp_path / "forbidden.json"
    for extra in (["--save", str(target)], ["--max-search-nodes", "1000000"]):
        assert subprocess.run(
            cmd + extra, capture_output=True, timeout=20,
        ).returncode == 2
    assert not target.exists()
