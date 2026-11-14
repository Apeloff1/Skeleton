"""Standalone exported game package can be played through user-facing CLI."""
import json
import subprocess
import sys
from pathlib import Path
from skeleton.game.gameplay.ridge_rescue.acceptance import ACCEPTANCE_SOURCE, acceptance_actions

def run(*args):
    return subprocess.run([sys.executable, "-m", "skeleton.game.gameplay.ridge_rescue.package_cli", *args], capture_output=True, text=True, timeout=15)

def test_export_verify_and_play_source_bound_game(tmp_path):
    package = tmp_path / "cinder.game.json"
    build = run("build", "--world", str(ACCEPTANCE_SOURCE), "--output", str(package))
    assert build.returncode == 0, build.stderr
    verified = run("verify", "--package", str(package))
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["valid"] is True
    output = tmp_path / "cinder.run.json"
    play = run("play", "--package", str(package), "--actions", json.dumps(acceptance_actions("protect")), "--output", str(output))
    assert play.returncode == 0, play.stderr
    assert json.loads(output.read_text())["payload"]["state"]["status"] == "won:protect"

def test_export_refuses_overwrite(tmp_path):
    target = tmp_path / "existing.game.json"
    target.write_text("original")
    build = run("build", "--world", str(ACCEPTANCE_SOURCE), "--output", str(target))
    assert build.returncode != 0
    assert target.read_text() == "original"
