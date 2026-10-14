from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import scripts.run_feature_unit_tests as runner


def _touch(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_example(): pass\n", encoding="utf-8")


def test_feature_discovery_across_all_roots_and_deduplication(tmp_path: Path) -> None:
    _touch(tmp_path, "tests/test_ai_game_builder.py")
    _touch(tmp_path, "skeleton/testing/test_ai_model_routing.py")
    _touch(tmp_path, "backend/tests/test_ai_provider.py")
    _touch(tmp_path, "tests/test_physics.py")
    assert runner.discover_tests(tmp_path, ["ai", "game-builder", "ai"]) == [
        "backend/tests/test_ai_provider.py",
        "skeleton/testing/test_ai_model_routing.py",
        "tests/test_ai_game_builder.py",
    ]


def test_nested_feature_directory_is_discovered(tmp_path: Path) -> None:
    _touch(tmp_path, "tests/flgb/test_world_contract.py")
    _touch(tmp_path, "tests/ai_pipeline/test_text_pipeline.py")
    assert runner.discover_tests(tmp_path, ["game-builder"]) == [
        "tests/flgb/test_world_contract.py"
    ]
    assert runner.discover_tests(tmp_path, ["ai"]) == [
        "tests/ai_pipeline/test_text_pipeline.py"
    ]


def test_only_complete_markers_match(tmp_path: Path) -> None:
    _touch(tmp_path, "tests/test_email.py")
    _touch(tmp_path, "tests/test_ai.py")
    _touch(tmp_path, "tests/test_aircraft.py")
    assert runner.discover_tests(tmp_path, ["ai"]) == ["tests/test_ai.py"]


def test_unit_default_excludes_e2e_integration_live_and_can_opt_in(tmp_path: Path) -> None:
    for filename in ("test_dragon.py", "test_dragon_e2e.py", "test_dragon_integration.py", "test_dragon_live.py"):
        _touch(tmp_path, f"tests/{filename}")
    assert runner.discover_tests(tmp_path, ["dragon"]) == ["tests/test_dragon.py"]
    assert len(runner.discover_tests(tmp_path, ["dragon"], include_integration=True)) == 4


def test_backend_and_all_have_explicit_scope(tmp_path: Path) -> None:
    _touch(tmp_path, "backend/tests/test_routes.py")
    _touch(tmp_path, "tests/test_routes.py")
    _touch(tmp_path, "skeleton/testing/test_routes.py")
    assert runner.discover_tests(tmp_path, ["backend"]) == ["backend/tests/test_routes.py"]
    assert len(runner.discover_tests(tmp_path, ["all"])) == 3


def test_no_matching_file_fails_closed(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    assert runner.main(["--feature", "physics"]) == 2
    assert "refusing a false-green" in capsys.readouterr().err


def test_list_mode_does_not_spawn_pytest(tmp_path: Path, monkeypatch, capsys) -> None:
    _touch(tmp_path, "tests/test_jeeves.py")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert runner.main(["--feature", "jeeves", "--list"]) == 0
    assert "tests/test_jeeves.py" in capsys.readouterr().out


def test_exit_status_is_preserved_and_external_plugins_disabled(tmp_path: Path, monkeypatch) -> None:
    _touch(tmp_path, "tests/test_security.py")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("PYTEST_ADDOPTS", "--ignore=tests")
    captured = {}

    def fake_run(command, *, cwd, env, check):
        captured.update(command=command, cwd=cwd, env=env, check=check)
        return SimpleNamespace(returncode=5)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main(["--feature", "security", "--junitxml", "report.xml"]) == 5
    assert captured["cwd"] == tmp_path
    assert captured["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert "PYTEST_ADDOPTS" not in captured["env"]
    assert "--junitxml=report.xml" in captured["command"]
    assert "tests/test_security.py" in captured["command"]


def test_reject_negative_maxfail(tmp_path: Path, monkeypatch) -> None:
    import pytest

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as exc:
        runner.main(["--feature", "ai", "--maxfail", "-1"])
    assert exc.value.code == 2


def test_integration_directories_are_excluded_by_default(tmp_path: Path) -> None:
    _touch(tmp_path, "tests/integration/test_dragon.py")
    _touch(tmp_path, "skeleton/testing/live/test_dragon.py")
    _touch(tmp_path, "backend/tests/e2e/test_dragon.py")
    _touch(tmp_path, "tests/test_dragon.py")
    assert runner.discover_tests(tmp_path, ["dragon"]) == ["tests/test_dragon.py"]
    assert len(runner.discover_tests(tmp_path, ["dragon"], include_integration=True)) == 4


def test_symlinked_test_file_is_not_followed(tmp_path: Path) -> None:
    import pytest

    external = tmp_path.parent / "outside-unit-target.py"
    external.write_text("def test_dragon(): pass\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    try:
        (tmp_path / "tests" / "test_dragon.py").symlink_to(external)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation unavailable")
    assert runner.discover_tests(tmp_path, ["dragon"]) == []


def test_collect_only_uses_actual_pytest_collection(tmp_path: Path, monkeypatch) -> None:
    _touch(tmp_path, "tests/test_ai.py")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    called = {}

    def fake_run(command, **kwargs):
        called.update(command=command, kwargs=kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main(["--feature", "ai", "--collect-only"]) == 0
    assert "--collect-only" in called["command"]
    assert "tests/test_ai.py" in called["command"]


def test_subprocess_timeout_is_nonzero_and_bounded(tmp_path: Path, monkeypatch, capsys) -> None:
    import subprocess

    _touch(tmp_path, "tests/test_jeeves.py")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    called = {}

    def timeout_run(command, **kwargs):
        called.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(runner.subprocess, "run", timeout_run)
    assert runner.main(["--feature", "jeeves", "--timeout-seconds", "2"]) == 124
    assert called["timeout"] == 2
    assert "wall-time" in capsys.readouterr().err


def test_spawn_failure_is_nonzero(tmp_path: Path, monkeypatch, capsys) -> None:
    _touch(tmp_path, "tests/test_jeeves.py")
    monkeypatch.setattr(runner, "ROOT", tmp_path)

    def failed_run(command, **kwargs):
        raise OSError("simulated spawn failure")

    monkeypatch.setattr(runner.subprocess, "run", failed_run)
    assert runner.main(["--feature", "jeeves"]) == 126
    assert "simulated spawn failure" in capsys.readouterr().err


def test_invalid_timeout_is_rejected(monkeypatch, tmp_path: Path) -> None:
    import pytest

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as exc:
        runner.main(["--feature", "ai", "--timeout-seconds", "-5"])
    assert exc.value.code == 2
