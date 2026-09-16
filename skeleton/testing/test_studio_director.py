from __future__ import annotations

import json

import pytest

from skeleton.automation.studio_director import (
    AuditLog,
    _canonical_path,
    _changed_paths,
    _extract_json,
    _parse_task,
    _redact_value,
)


def test_extract_json_accepts_plain_and_fenced_payloads() -> None:
    assert _extract_json('{"tasks": []}') == {"tasks": []}
    assert _extract_json('```json\n{"tasks": []}\n```') == {"tasks": []}


def test_path_policy_allows_normal_source_and_rejects_trust_boundaries() -> None:
    assert _canonical_path("skeleton/gameplay/core.py") == "skeleton/gameplay/core.py"
    assert _canonical_path("backend/api.py") == "backend/api.py"

    for path in (
        "../escape.py",
        ".github/workflows/pwn.yml",
        ".env",
        "pyproject.toml",
        "skeleton/security/auth.py",
        "random-root/file.py",
    ):
        with pytest.raises(ValueError):
            _canonical_path(path)


def test_task_parser_requires_known_division_and_bounded_paths() -> None:
    task = _parse_task(
        {
            "title": "Improve mechanics",
            "objective": "Strengthen deterministic combat resolution.",
            "division": "gameplay_systems",
            "paths": ["skeleton/gameplay/core.py"],
        }
    )
    assert task.division == "gameplay_systems"

    with pytest.raises(ValueError):
        _parse_task(
            {
                "title": "x",
                "objective": "y",
                "division": "made_up",
                "paths": ["skeleton/gameplay/core.py"],
            }
        )


def test_patch_parser_prevents_scope_escape_rename_and_delete() -> None:
    patch = """diff --git a/skeleton/foo.py b/skeleton/foo.py
index 1111111..2222222 100644
--- a/skeleton/foo.py
+++ b/skeleton/foo.py
@@ -1 +1 @@
-old
+new
"""
    assert _changed_paths(patch) == ("skeleton/foo.py",)

    escaped = patch.replace("skeleton/foo.py", ".github/workflows/foo.yml")
    with pytest.raises(ValueError):
        _changed_paths(escaped)

    deleted = patch.replace("+++ b/skeleton/foo.py", "+++ /dev/null")
    with pytest.raises(ValueError):
        _changed_paths(deleted)


def test_redaction_preserves_nested_json_shapes() -> None:
    value = {
        "outer": [
            "api_key=super-secret",
            {"authorization": "Authorization: Bearer another-secret"},
        ]
    }
    redacted = _redact_value(value)
    encoded = json.dumps(redacted)
    decoded = json.loads(encoded)
    assert decoded["outer"][0] == "api_key=[REDACTED]"
    assert "another-secret" not in encoded


def test_audit_log_redacts_secret_like_values_without_corrupting_json(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path, "run-1")
    audit.emit("test", value="api_key=super-secret", nested={"token": "token=abc123"})
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["run_id"] == "run-1"
    assert "super-secret" not in path.read_text(encoding="utf-8")
    assert "abc123" not in path.read_text(encoding="utf-8")
    assert "[REDACTED]" in row["value"]
