"""End-user CLI smoke, portable export, verify and safe no-overwrite behavior."""
import json
import os
from pathlib import Path
import subprocess
import sys

def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "skeleton.game.gameplay.ridge_rescue.cli", *args], capture_output=True, text=True, timeout=15)

def test_inspect_cli():
    result = run_cli("inspect")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["civilians"] == 2

def test_play_and_verify_portable_bundle(tmp_path):
    target = tmp_path / "run.json"
    result = run_cli("play", "--actions", '[{"verb":"rest"}]', "--output", str(target))
    assert result.returncode == 0, result.stderr
    assert target.is_file()
    verified = run_cli("verify", "--bundle", str(target))
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["valid"] is True
    second = run_cli("play", "--output", str(target))
    assert second.returncode != 0
    assert json.loads(target.read_text())["payload"]["actions"] == [{"verb": "rest"}]

def test_tampered_bundle_rejected(tmp_path):
    path = tmp_path / "tampered.json"
    path.write_text('{"payload":{"schema":"ridge.rescue.run.v1"},"sha256":"bad"}')
    result = run_cli("verify", "--bundle", str(path))
    assert result.returncode != 0

def test_author_cli():
    result = run_cli("author", "--operation", '{"kind":"rename","target":"world","value":"New Cinder"}')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["world"]["name"] == "New Cinder"

def test_invalid_actions_refused():
    result = run_cli("play", "--actions", '[{"verb":"move","direction":"west"}]')
    assert result.returncode != 0
