"""Real end-user CLI demo must win from authored source and independently verify."""
import json
import subprocess
import sys
from pathlib import Path

def run(*args):
    return subprocess.run([sys.executable, "-m", "skeleton.game.gameplay.ridge_rescue.cli", *args], capture_output=True, text=True, timeout=15)

def test_demo_produces_replay_verified_protect_ending(tmp_path):
    target = tmp_path / "first-rescue.json"
    result = run("demo", "--output", str(target))
    assert result.returncode == 0, result.stderr
    bundle = json.loads(target.read_text())
    assert bundle["payload"]["state"]["status"] == "won:protect"
    assert bundle["payload"]["state"]["flags"]["beacon"] is True
    verify = run("verify", "--bundle", str(target))
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["valid"] is True

def test_demo_does_not_overwrite_existing_export(tmp_path):
    target = tmp_path / "first-rescue.json"
    target.write_text("preserve")
    result = run("demo", "--output", str(target))
    assert result.returncode != 0
    assert target.read_text() == "preserve"
