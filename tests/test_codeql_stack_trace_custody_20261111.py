"""Source-wide guard for the 125 historical CodeQL exception disclosures.

The 151-alert inventory is the source of truth for file selection. This test
does not claim those alerts have been resolved; it rejects reintroduction of
obvious raw exception sinks in any of their 49 affected Python source files.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/security/codeql-open-151-lineage-2026-11-11.json"
PUBLIC_KEYS = {"error", "detail", "message", "traceback", "stack", "exception"}


def _exception_value_leaks(value: ast.AST, name: str) -> bool:
    """Find direct error values without treating type(exc).__name__ as secret."""
    if isinstance(value, ast.Name) and value.id == name:
        return True
    if isinstance(value, ast.Call):
        if isinstance(value.func, ast.Name) and value.func.id == "type":
            return False
        if isinstance(value.func, ast.Name) and value.func.id in {"str", "repr"}:
            return any(_exception_value_leaks(item, name) for item in value.args)
    if isinstance(value, ast.FormattedValue):
        return _exception_value_leaks(value.value, name)
    if isinstance(value, ast.JoinedStr):
        return any(_exception_value_leaks(part, name) for part in value.values)
    if isinstance(value, ast.BinOp):
        return (
            _exception_value_leaks(value.left, name)
            or _exception_value_leaks(value.right, name)
        )
    if isinstance(value, ast.Attribute):
        return _exception_value_leaks(value.value, name)
    return False


def _raw_public_exception_sinks(tree: ast.AST) -> list[int]:
    leaking_lines = []
    for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
        if not handler.name:
            continue
        name = handler.name
        for statement in handler.body:
            for candidate in ast.walk(statement):
                if isinstance(candidate, ast.Call) and (
                    isinstance(candidate.func, ast.Name)
                    and candidate.func.id == "HTTPException"
                ):
                    # Only inspect HTTPException constructor detail values;
                    # exception chaining (from exc) stays server-side.
                    for item in candidate.args[1:]:
                        if _exception_value_leaks(item, name):
                            leaking_lines.append(candidate.lineno)
                    for keyword in candidate.keywords:
                        if keyword.arg == "detail" and _exception_value_leaks(keyword.value, name):
                            leaking_lines.append(candidate.lineno)
                if not isinstance(candidate, ast.Return):
                    continue
                value = candidate.value
                if isinstance(value, ast.Dict):
                    for key, field in zip(value.keys, value.values):
                        if isinstance(key, ast.Constant) and key.value in PUBLIC_KEYS:
                            if _exception_value_leaks(field, name):
                                leaking_lines.append(candidate.lineno)
    return sorted(set(leaking_lines))


def test_all_125_reported_stack_exposure_source_files_have_no_raw_public_sinks():
    snapshot = json.loads(LEDGER.read_text(encoding="utf-8"))
    source_paths = sorted({
        finding["path"] for finding in snapshot["findings"]
        if finding["rule_id"] == "py/stack-trace-exposure"
    })
    assert len(source_paths) == 49
    errors = {}
    for relative in source_paths:
        file = ROOT / relative
        assert file.is_file(), f"CodeQL inventory source missing: {relative}"
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=relative)
        findings = _raw_public_exception_sinks(tree)
        if findings:
            errors[relative] = findings
    assert not errors, f"Unredacted exception details found at {errors}"


def test_known_indirect_traceback_serializers_remain_removed():
    paths = (
        "backend/routes/galaxy_studio.py",
        "backend/routes/godot_engine.py",
        "backend/gameforge/api/scim.py",
        "backend/routes/prood.py",
        "backend/routes/jeeves_persona.py",
    )
    for relative in paths:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "traceback.print_exc()" not in text
        assert "detail=str(e)" not in text
        assert '"error": str(e)' not in text
        assert 'logger.warning(f"persona load failed: {e}")' not in text
