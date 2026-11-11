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


def _quorum_validation_contract(source: str) -> dict:
    """Verify the real route catches only constructor validation failures.

    Inspect repository source without compiling or executing a function extracted
    from a privileged route module. This is intentionally strict: a broader
    catch, changed constructor arguments or a nonliteral response fails closed.
    """
    tree = ast.parse(source)
    function = next(
        stmt for stmt in tree.body
        if isinstance(stmt, ast.AsyncFunctionDef) and stmt.name == "run_quorum"
    )
    guarded = next(stmt for stmt in function.body if isinstance(stmt, ast.Try))
    assert len(guarded.body) == 1
    assignment = guarded.body[0]
    assert isinstance(assignment, ast.Assign)
    assert len(assignment.targets) == 1
    assert isinstance(assignment.targets[0], ast.Name)
    assert assignment.targets[0].id == "qc"
    constructor = assignment.value
    assert isinstance(constructor, ast.Call)
    assert isinstance(constructor.func, ast.Name)
    assert constructor.func.id == "QuorumConsensus"
    assert [(item.arg, ast.unparse(item.value)) for item in constructor.keywords] == [
        ("n", "req.n"), ("f", "req.f")
    ]
    assert not constructor.args
    assert len(guarded.handlers) == 1
    handler = guarded.handlers[0]
    assert isinstance(handler.type, ast.Name) and handler.type.id == "ValueError"
    assert handler.name is None
    assert len(handler.body) == 1 and isinstance(handler.body[0], ast.Return)
    assert not guarded.orelse and not guarded.finalbody
    return ast.literal_eval(handler.body[0].value)


def test_prood_invalid_quorum_returns_stable_public_status():
    source = (_ROOT / "routes" / "prood.py").read_text(encoding="utf-8")
    assert _quorum_validation_contract(source) == {
        "ok": False, "error": "invalid_quorum_configuration"
    }


@pytest.mark.parametrize("mutation", [
    ("except ValueError:", "except Exception:"),
    ("QuorumConsensus(n=req.n, f=req.f)", "QuorumConsensus(n=7, f=2)"),
    ('"invalid_quorum_configuration"', '"private exception detail"'),
])
def test_prood_quorum_contract_rejects_broadened_or_leaking_edits(mutation):
    source = (_ROOT / "routes" / "prood.py").read_text(encoding="utf-8")
    old, new = mutation
    assert old in source
    with pytest.raises(AssertionError):
        response = _quorum_validation_contract(source.replace(old, new, 1))
        assert response == {"ok": False, "error": "invalid_quorum_configuration"}
