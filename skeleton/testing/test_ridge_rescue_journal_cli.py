"""CLI journal source -> save -> replay -> fork -> export -> import."""
import json
from pathlib import Path
import subprocess
import sys

def run(*args):
    return subprocess.run([sys.executable, "-m", "skeleton.game.gameplay.ridge_rescue.journal_cli", *args], capture_output=True, text=True, timeout=15)

def test_journal_cli_end_to_end(tmp_path):
    initial = tmp_path / "initial.json"
    result = run("init", "--output", str(initial))
    assert result.returncode == 0, result.stderr
    head = json.loads(initial.read_text())["head"]
    second = tmp_path / "second.json"
    result = run("append", "--journal", str(initial), "--expected", head, "--action", '{"verb":"rest"}', "--output", str(second))
    assert result.returncode == 0, result.stderr
    verified = run("verify", "--journal", str(second))
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["turn"] == 1
    bundle = tmp_path / "bundle.json"
    assert run("export", "--journal", str(second), "--output", str(bundle)).returncode == 0
    imported = tmp_path / "imported.json"
    assert run("import", "--bundle", str(bundle), "--output", str(imported)).returncode == 0
    assert json.loads(imported.read_text()) == json.loads(second.read_text())
    fork = tmp_path / "fork.json"
    current = json.loads(second.read_text())["head"]
    assert run("fork", "--journal", str(second), "--expected", current, "--sequence", "0", "--output", str(fork)).returncode == 0
    assert json.loads(fork.read_text()) == json.loads(initial.read_text())

def test_stale_cas_and_overwrite_are_refused(tmp_path):
    initial = tmp_path / "initial.json"
    assert run("init", "--output", str(initial)).returncode == 0
    result = run("append", "--journal", str(initial), "--expected", "f" * 64, "--action", '{"verb":"rest"}')
    assert result.returncode != 0
    result = run("init", "--output", str(initial))
    assert result.returncode != 0
