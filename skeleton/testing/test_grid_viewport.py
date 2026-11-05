"""Playable grid camera: clipping, accessibility, replay and CLI."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Command, Session
from skeleton.game.gameplay.grid_viewport import viewport

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "skeleton/game/gameplay/content/lantern_harbor.json"


def start() -> Session:
    return Session.new(Campaign.load(json.loads(FIXTURE.read_text())))


def test_camera_is_pure_and_player_is_visible() -> None:
    session = start()
    before = session.snapshot()
    camera = viewport(session, 5, 5)
    assert camera.rows[session.y - camera.origin_y][session.x - camera.origin_x] == "@"
    assert "Player at" in camera.description
    assert "health 10" in camera.description
    assert session.snapshot() == before


def test_camera_clamps_and_matches_full_map_when_larger() -> None:
    session = start()
    full = viewport(session, 64, 64)
    assert full.render() == session.render()
    assert full.origin_x == 0 and full.origin_y == 0
    assert full.width == len(session.campaign.spec["rows"][0])


def test_camera_follows_real_movement_without_changing_replay() -> None:
    session = start()
    initial = viewport(session, 3, 3)
    # A valid move must use canonical collision and event rules.
    for direction in ("north", "south", "east", "west"):
        try:
            moved = session.step(Command("camera-move", "move", direction))
        except GameplayContractError:
            continue
        camera = viewport(moved, 3, 3)
        assert (camera.player_x, camera.player_y) == (moved.x, moved.y)
        assert camera.render() != "" and moved.state_digest != session.state_digest
        assert Session.restore(session.campaign, moved.snapshot()).state_digest == (
            moved.state_digest
        )
        assert initial.record() != camera.record()
        break
    else:
        pytest.skip("authored starting tile has no legal neighboring movement")


@pytest.mark.parametrize("width,height", [
    (0, 5), (2, 5), (5, 65), (True, 5), (5, -1),
])
def test_invalid_camera_sizes_fail_closed(width, height) -> None:
    with pytest.raises(GameplayContractError):
        viewport(start(), width, height)


def test_installed_cli_exposes_accessible_camera_without_gameplay_mutation() -> None:
    cmd = [sys.executable, "-m", "scripts.game.offline_grid_campaign",
           "inspect", "--source", str(FIXTURE),
           "--view-width", "5", "--view-height", "5", "--accessible"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["viewport"]["size"] == [5, 5]
    assert "Player at" in payload["viewport"]["description"]
    assert "@" in "".join(payload["viewport"]["rows"])


def test_cli_rejects_unbounded_viewport() -> None:
    cmd = [sys.executable, "-m", "scripts.game.offline_grid_campaign",
           "inspect", "--source", str(FIXTURE), "--view-width", "1000000"]
    assert subprocess.run(cmd, capture_output=True, timeout=20).returncode == 2
