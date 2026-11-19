"""Contract tests for real Compose CLI rendering qualification.

No Docker daemon, model or GPU is needed for this source-only unit suite.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from scripts import qualify_local_ai_compose as qual
from scripts import local_ai_docker as host
from skeleton.testing.test_docker_local_ai import _fake_config


def test_compose_source_qualification_requires_all_three_modes(tmp_path: Path) -> None:
    fake = _fake_config(tmp_path)
    class Result:
        returncode = 0
        stdout = json.dumps(fake)
    def rendering(args, **kwargs):
        assert "--format" in args
        assert kwargs["capture_output"] is True
        assert kwargs["env"]["OPENAI_API_KEY"] == ""
        return Result()
    # The test config's GPU profiles are deliberately incomplete, and must
    # not be treated as qualified merely because Docker returned zero.
    with mock.patch.object(qual.subprocess, "run", side_effect=rendering):
        with pytest.raises(host.LocalDockerError):
            qual.qualify(tmp_path)


def test_invalid_compose_response_never_echoes_private_content(tmp_path: Path) -> None:
    class Result:
        returncode = 1
        stdout = "mongodb://" + "operator:synthetic@secret"
        stderr = "private synthetic credential"
    with mock.patch.object(qual.subprocess, "run", return_value=Result()):
        with pytest.raises(host.LocalDockerError, match="configuration failed") as error:
            qual.qualify(tmp_path)
    assert "synthetic credential" not in str(error.value)
    assert "mongodb" not in str(error.value)


def test_profile_cli_source_never_builds_or_activates_models() -> None:
    source = Path(qual.__file__).read_text(encoding="utf-8")
    assert '"config", "--format", "json"' in source
    assert 'docker", "compose"' in source
    assert '"up", "-d"' not in source
    assert '"build", "skeleton"' not in source


def test_compose_source_cli_imports_under_isolated_python(tmp_path: Path) -> None:
    import subprocess
    import sys

    module_path = Path(qual.__file__).resolve()
    # Do not run the Docker qualification here: importing a standalone
    # operator script must work without PYTHONPATH or a daemon.
    command = [
        sys.executable, "-I", "-c",
        "import runpy; runpy.run_path(" + repr(str(module_path)) + ", run_name='source_only')",
    ]
    completed = subprocess.run(
        command, cwd=tmp_path, capture_output=True, text=True, timeout=15,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[:500]
