"""Fail-closed source-path and pytest-selector admission for Draft19 CI.

Static validation only: no imports of test files, no execution, no network I/O.
The actual tests and all independent release gates still have to run.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path, PurePosixPath
import re

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = ".github/workflows/draft19-gguf-source-qualification.yml"
# Paths used by py_compile, pytest, and direct Python script invocations.
_SOURCE = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(?P<path>(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.py)"
    r"(?:::(?P<test>test_[A-Za-z0-9_]+))?"
)
MAX_WORKFLOW_BYTES = 128 * 1024
MAX_PY_SOURCE_BYTES = 4 * 1024 * 1024
MAX_REFERENCES = 256


def validate_ci_paths(root: Path, workflow: str = _WORKFLOW) -> tuple[str, ...]:
    """Return stable errors for every missing or mismatched source reference."""
    root = root.resolve()
    rel_workflow = PurePosixPath(workflow)
    if rel_workflow.is_absolute() or ".." in rel_workflow.parts:
        return ("invalid workflow path",)
    workflow_path = root.joinpath(*rel_workflow.parts)
    if not workflow_path.is_file() or workflow_path.is_symlink():
        return ("workflow missing or symbolic",)
    if workflow_path.stat().st_size > MAX_WORKFLOW_BYTES:
        return ("workflow exceeds path-check budget",)
    try:
        content = workflow_path.read_text(encoding="utf-8")
    except (UnicodeError, OSError):
        return ("workflow is not readable UTF-8",)
    refs = [(match.group("path"), match.group("test"))
            for match in _SOURCE.finditer(content)]
    if not refs:
        return ("workflow has no literal Python source references",)
    if len(refs) > MAX_REFERENCES:
        return ("workflow exceeds source-reference budget",)
    errors: list[str] = []
    checked: set[tuple[str, str | None]] = set()
    cached_definitions: dict[str, set[str]] = {}
    for path, test in refs:
        key = (path, test)
        # Repeated compile references are harmless. Repeated test selectors
        # are not: silently doubling a selector can mask suite substitutions.
        if key in checked and test is not None:
            errors.append(f"duplicate pytest selector: {path}::{test}")
        checked.add(key)
        rel = PurePosixPath(path)
        if rel.is_absolute() or any(p in ("..", ".") for p in rel.parts):
            errors.append(f"unsafe source path: {path}")
            continue
        candidate = root.joinpath(*rel.parts)
        if any(root.joinpath(*rel.parts[:idx]).is_symlink()
               for idx in range(1, len(rel.parts) + 1)):
            errors.append(f"symbolic source path: {path}")
            continue
        if not candidate.is_file():
            errors.append(f"missing source: {path}")
            continue
        if test is None:
            continue
        if path not in cached_definitions:
            if candidate.stat().st_size > MAX_PY_SOURCE_BYTES:
                errors.append(f"test source exceeds parse budget: {path}")
                continue
            try:
                code = candidate.read_text(encoding="utf-8")
                tree = ast.parse(code, filename=path)
            except (SyntaxError, UnicodeError, OSError):
                errors.append(f"test source cannot be parsed: {path}")
                continue
            cached_definitions[path] = {
                node.name for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        if test not in cached_definitions.get(path, set()):
            errors.append(f"missing pytest selector: {path}::{test}")
    return tuple(sorted(set(errors)))


def main() -> int:
    issues = validate_ci_paths(_ROOT)
    print(json.dumps({
        "schema": "skeleton.ci.literal_pytest_path_qualification.v1",
        "qualified": not issues,
        "errors": issues,
        "test_execution_claimed": False,
        "release_certified": False,
    }, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
