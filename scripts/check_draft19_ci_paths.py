"""Fail-closed source-path and pytest-selector admission for Draft19 CI.

Static validation only: no imports of test files, no execution, no network I/O.
The actual tests and all independent release gates still have to run.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path, PurePosixPath
import re
import shlex

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



_UNITTEST_COMMAND = re.compile(
    r"(?m)^[ \t]*(?:run:[ \t]*)?python[ \t]+-m[ \t]+unittest[ \t]+(?P<args>[^\r\n#]+)"
)
_DOTTED_MODULE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", re.ASCII)
_DISCOVERY_FILE = re.compile(r"test_[A-Za-z0-9_]+\.py", re.ASCII)


def _literal_unittest_paths(content: str) -> tuple[list[str], list[str]]:
    """Admit only the literal unittest forms used by this qualification lane.

    unittest discovery can exit successfully after collecting zero tests when
    an old pattern no longer matches. Dotted modules and discovery patterns
    are invisible to the ordinary slash-delimited source regex.
    """
    paths: list[str] = []
    errors: list[str] = []
    for match in _UNITTEST_COMMAND.finditer(content):
        try:
            args = shlex.split(match.group("args"), comments=False, posix=True)
        except ValueError:
            errors.append("malformed unittest command")
            continue
        args = [
            arg for arg in args if arg not in ("-v", "--verbose")
        ]
        if not args:
            errors.append("unittest command has no explicit source")
        elif args[0] == "discover":
            if (
                len(args) != 5 or args[1] != "-s" or args[3] != "-p"
                or args[2] != "tests" or not _DISCOVERY_FILE.fullmatch(args[4])
            ):
                errors.append("unsupported unittest discovery scope or pattern")
                continue
            paths.append("tests/" + args[4])
        elif all(_DOTTED_MODULE.fullmatch(arg) for arg in args):
            paths.extend(arg.replace(".", "/") + ".py" for arg in args)
        else:
            errors.append("unsupported unittest module selection")
    return paths, errors


def _has_unittest_candidates(tree: ast.Module) -> bool:
    # This is static admission, not a claim of actual unittest collection:
    # explicit load_tests hooks may construct cases dynamically.
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "load_tests":
            return True
        if isinstance(node, ast.ClassDef) and any(
            isinstance(method, ast.FunctionDef) and method.name.startswith("test")
            for method in node.body
        ):
            return True
    return False


def validate_ci_paths(root: Path, workflow: str = _WORKFLOW) -> tuple[str, ...]:
    """Return stable errors for every missing or mismatched source reference."""
    root = root.resolve()
    rel_workflow = PurePosixPath(workflow)
    if rel_workflow.is_absolute() or ".." in rel_workflow.parts:
        return ("invalid workflow path",)
    workflow_path = root.joinpath(*rel_workflow.parts)
    if any(root.joinpath(*rel_workflow.parts[:idx]).is_symlink()
           for idx in range(1, len(rel_workflow.parts) + 1)) or not workflow_path.is_file():
        return ("workflow missing or symbolic",)
    if workflow_path.stat().st_size > MAX_WORKFLOW_BYTES:
        return ("workflow exceeds path-check budget",)
    try:
        content = workflow_path.read_text(encoding="utf-8")
    except (UnicodeError, OSError):
        return ("workflow is not readable UTF-8",)
    refs = [(match.group("path"), match.group("test"))
            for match in _SOURCE.finditer(content)]
    unittest_paths, errors = _literal_unittest_paths(content)
    refs.extend((path, None) for path in unittest_paths)
    if not refs and not errors:
        return ("workflow has no literal Python source references",)
    if len(refs) > MAX_REFERENCES:
        return ("workflow exceeds source-reference budget",)
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
        if path in unittest_paths:
            try:
                if candidate.stat().st_size > MAX_PY_SOURCE_BYTES:
                    errors.append(f"unittest source exceeds parse budget: {path}")
                elif not _has_unittest_candidates(ast.parse(candidate.read_text(encoding="utf-8"), filename=path)):
                    errors.append(f"unittest source has no static test candidates: {path}")
            except (OSError, UnicodeError, SyntaxError):
                errors.append(f"unittest source cannot be parsed: {path}")
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
