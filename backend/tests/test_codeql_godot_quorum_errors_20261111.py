"""No-device regression: Godot/PROOD HTTP responses must hide private exceptions."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from routes import godot_engine as godot

_ROOT = Path(__file__).resolve().parents[1]


def test_godot_errors_cannot_echo_private_paths_or_source(monkeypatch, tmp_path):
    secret = "/private/project/secret-source-token"
    with pytest.raises(ValueError) as result:
        godot._safe_segment("../" + secret)
    assert secret not in str(result.value)

    with pytest.raises(HTTPException) as error:
        godot._resolve_within(tmp_path, "../" + secret, "input")
    assert error.value.status_code == 422
    assert secret not in str(error.value.detail)

    monkeypatch.setattr(godot, "_PROJECTS_ROOT", tmp_path)
    with pytest.raises(HTTPException) as error:
        godot._project_dir_for("../" + secret)
    assert error.value.status_code == 422
    assert secret not in str(error.value.detail)


def test_create_project_redacts_internal_validation_errors(monkeypatch, tmp_path):
    secret = "sensitive Godot project config"
    monkeypatch.setattr(godot, "_PROJECTS_ROOT", tmp_path)

    def bad_project(*args, **kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(godot, "scaffold_project", bad_project)
    with pytest.raises(HTTPException) as result:
        asyncio.run(godot.create_project(godot.ProjectCreateRequest(title="Hello")))
    assert result.value.status_code == 422
    assert secret not in str(result.value.detail)


def test_job_validation_redacts_backend_exception(monkeypatch):
    secret = "confidential export path"

    class Pipeline:
        async def submit(self, *_args, **_kwargs):
            raise ValueError(secret)

    monkeypatch.setattr(godot, "code_execution_enabled", lambda: True)
    monkeypatch.setattr(godot, "get_pipeline", lambda: Pipeline())
    with pytest.raises(HTTPException) as result:
        asyncio.run(godot.submit_job(godot.JobSubmitRequest(kind="import")))
    assert result.value.status_code == 422
    assert secret not in str(result.value.detail)


def test_godot_public_job_never_returns_stacks_source_or_stdout():
    class Job:
        def to_dict(self):
            return {
                "id": "safe", "kind": "check", "status": "failed",
                "created_at": 0.5,
                "result": {
                    "returncode": 12,
                    "stdout_tail": ["api_key=private-secret"],
                    "stderr_tail": ["Traceback secret"],
                },
                "error": "private traceback and database DSN",
            }

    result = godot._public_job(Job())
    assert result["result"] == {"returncode": 12}
    assert result["error"] == "godot_job_failed"
    assert "private" not in str(result)
    assert "Traceback" not in str(result)
    assert "stdout_tail" not in result
    assert "stderr_tail" not in result


def test_prood_invalid_quorum_returns_stable_public_status():
    # Extract the handler without importing the PROOD runtime's DB/device
    # dependencies. Exercise its real exception path with a failing actor.
    source = (_ROOT / "routes" / "prood.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        stmt for stmt in tree.body
        if isinstance(stmt, ast.AsyncFunctionDef) and stmt.name == "run_quorum"
    )
    function.decorator_list = []
    function.args.args[0].annotation = None

    class InvalidQuorum:
        def __init__(self, **_kwargs):
            raise ValueError("secret internal quorum configuration")

    env = {"QuorumConsensus": InvalidQuorum}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "prood.py", "exec"), env)
    req = type("Request", (), {"n": -2, "f": 99})()
    result = asyncio.run(env["run_quorum"](req))
    assert result == {"ok": False, "error": "invalid_quorum_configuration"}
