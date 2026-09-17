import json

from core.shift_supervisor.__main__ import _context, main


def test_entrypoint_reads_project_context_at_runtime(monkeypatch):
    monkeypatch.delenv("SHIFT_PROJECT_CONTEXT_FILE", raising=False)
    monkeypatch.setenv("SHIFT_PROJECT_CONTEXT_JSON", json.dumps({"repository": "Apeloff1/Skeleton"}))
    assert _context() == {"repository": "Apeloff1/Skeleton"}


def test_entrypoint_prefers_project_context_file(monkeypatch, tmp_path):
    path = tmp_path / "repo-state.json"
    path.write_text(json.dumps({"source": "workflow-file"}), encoding="utf-8")
    monkeypatch.setenv("SHIFT_PROJECT_CONTEXT_FILE", str(path))
    monkeypatch.setenv("SHIFT_PROJECT_CONTEXT_JSON", json.dumps({"source": "environment"}))

    assert _context() == {"source": "workflow-file"}


def test_entrypoint_refuses_unbounded_mode_in_github_actions(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    try:
        main([])
    except SystemExit as exc:
        assert "pass --once" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_entrypoint_reads_project_context_at_runtime(monkeypatch):
    monkeypatch.delenv("SHIFT_PROJECT_CONTEXT_FILE", raising=False)
    monkeypatch.setenv("SHIFT_PROJECT_CONTEXT_JSON", json.dumps({"repository": "Apeloff1/Skeleton"}))
    assert _context() == {"repository": "Apeloff1/Skeleton"}


def test_entrypoint_prefers_project_context_file(monkeypatch, tmp_path):
    path = tmp_path / "repo-state.json"
    path.write_text(json.dumps({"source": "workflow-file"}), encoding="utf-8")
    monkeypatch.setenv("SHIFT_PROJECT_CONTEXT_FILE", str(path))
    monkeypatch.setenv("SHIFT_PROJECT_CONTEXT_JSON", json.dumps({"source": "environment"}))

    assert _context() == {"source": "workflow-file"}
