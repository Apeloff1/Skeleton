"""Regression contract for the actual Compose Mongo health command."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("status", [0, 1, 17])
def test_mongo_health_shell_propagates_status(tmp_path, status):
    if not shutil.which("sh"):
        pytest.skip("POSIX shell required")
    probe = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]["mongo"]["healthcheck"]["test"]
    assert probe[0] == "CMD-SHELL"
    assert "quit(db.runCommand({ ping: 1 }).ok === 1 ? 0 : 1)" in probe[1]
    stub = tmp_path / "mongosh"
    stub.write_text("#!/bin/sh\nexit \"$PROBE_STATUS\"\n")
    stub.chmod(0o700)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
               PROBE_STATUS=str(status), MONGO_INITDB_ROOT_USERNAME="test",
               MONGO_INITDB_ROOT_PASSWORD="test password")
    result = subprocess.run(["sh", "-c", probe[1].replace("$$", "$")],
                            env=env, timeout=5, check=False)
    assert result.returncode == status
