"""CLI market operations and dispatch regression."""
from __future__ import annotations

import json
from pathlib import Path

from skeleton.game.gameplay.harbor_crafting import canonical, demo_actions, export_bundle, load_source
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_WORLD, main


def _save(root: Path, name: str, value: object) -> str:
    path = root / name
    path.write_bytes(canonical(value))
    return str(path)


def test_cli_market_roundtrip(tmp_path, capfd):
    bundle = export_bundle(load_source(DEFAULT_WORLD), demo_actions(), require_win=True)
    path = _save(tmp_path, "bundle.json", bundle)
    assert main(["market-report", "--bundle", path]) == 0
    report = json.loads(capfd.readouterr().out)
    assert report["totals"]["ending"] == "beacon"
    market_path = _save(tmp_path, "market.json", report)
    assert main(["verify-market", "--report", market_path]) == 0
    assert json.loads(capfd.readouterr().out)["verified"] is True
    assert main(["market-checkpoint", "--report", market_path, "--tick", str(len(demo_actions()) - 1)]) == 0
    partial = json.loads(capfd.readouterr().out)
    partial_path = _save(tmp_path, "partial.json", partial)
    suffix = _save(tmp_path, "actions.json", [demo_actions()[-1]])
    assert main([
        "market-resume", "--report", partial_path, "--actions", suffix,
        "--expected-terminal-digest", partial["terminal_digest"], "--require-win",
    ]) == 0
    assert json.loads(capfd.readouterr().out) == report


def test_cli_missing_inputs_are_rejected(capfd):
    assert main(["market-report"]) == 2
    assert "required" in capfd.readouterr().err
    assert main(["market-resume"]) == 2
    assert "required" in capfd.readouterr().err


def test_existing_mission_dispatch_not_overwritten(tmp_path, capfd):
    bundle = export_bundle(load_source(DEFAULT_WORLD), demo_actions(), require_win=True)
    path = _save(tmp_path, "bundle.json", bundle)
    assert main(["mission-report", "--bundle", path]) == 0
    result = json.loads(capfd.readouterr().out)
    assert "points" in result and "bundle" in result
    assert main(["verify", "--bundle", path, "--require-win"]) == 0
    assert json.loads(capfd.readouterr().out)["verified"] is True
