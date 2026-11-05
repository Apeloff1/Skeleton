"""Portable market game export, replay and CLI acceptance."""
from __future__ import annotations

import json
from pathlib import Path

from skeleton.game.gameplay.harbor_crafting import canonical, demo_actions
from skeleton.game.gameplay.harbor_crafting_cli import main


def _save(root: Path, name: str, value: object) -> str:
    path = root / name
    path.write_bytes(canonical(value))
    return str(path)


def test_cli_market_distribution_and_player_replay(tmp_path, capfd):
    assert main(["market-distribution"]) == 0
    distribution = json.loads(capfd.readouterr().out)
    path = _save(tmp_path, "distribution.json", distribution)
    assert main(["verify-market-distribution", "--package", path]) == 0
    assert json.loads(capfd.readouterr().out)["verified"] is True
    actions = _save(tmp_path, "actions.json", demo_actions())
    assert main([
        "market-distribution-play", "--package", path, "--actions", actions,
    ]) == 0
    session = json.loads(capfd.readouterr().out)
    session_path = _save(tmp_path, "session.json", session)
    assert main([
        "verify-market-distribution-play", "--play", session_path,
    ]) == 0
    assert json.loads(capfd.readouterr().out)["totals"]["ending"] == "beacon"
