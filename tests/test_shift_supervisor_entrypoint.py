import json

from core.shift_supervisor.__main__ import _context


def test_entrypoint_reads_project_context_at_runtime(monkeypatch):
    monkeypatch.setenv("SHIFT_PROJECT_CONTEXT_JSON", json.dumps({"repository": "Apeloff1/Skeleton"}))
    assert _context() == {"repository": "Apeloff1/Skeleton"}
