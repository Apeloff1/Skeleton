#!/usr/bin/env python3
"""Fail closed on high-risk Skeleton package boundary violations.

The gate combines the canonical Skeleton layering rules with repository-root production
boundaries. It intentionally stays dependency-free so it can run early in CI.
See docs/CANONICAL_MODULE_BOUNDARIES.md for the ownership contract.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SKELETON_ROOT = REPO_ROOT / "skeleton"
BACKEND_ROOT = REPO_ROOT / "backend"

_KERNEL_FORBIDDEN_ROOTS = {
    "fastapi",
    "flask",
    "django",
    "requests",
    "httpx",
    "sqlalchemy",
    "psycopg",
    "psycopg2",
    "pymongo",
    "redis",
    "aiohttp",
}

_PRODUCTION_RULES = (
    {
        "root": "skeleton",
        "excluded_prefixes": ("skeleton/testing/",),
        "forbidden_modules": ("backend", "frontend", "tests"),
    },
    {
        "root": "backend",
        "excluded_prefixes": ("backend/tests/",),
        "forbidden_modules": ("frontend", "tests", "skeleton.testing"),
    },
)

# Exact composition roots are allowed to assemble interface adapters. Keep this
# list deliberately tiny: adding a path is an architecture decision, not a CI
# escape hatch. Tests are handled separately through excluded_prefixes.
_API_COMPOSITION_ROOTS = {
    "skeleton/__main__.py",
    "skeleton/deploy/harness.py",
}

_AI_FILE_TREE_MIRROR_STATES = {"staged_mirror", "cutover_pending"}


def _staged_api_mirror_prefixes(repo_root: Path) -> tuple[str, ...]:
    """Return manifest-governed skeleton.api mirrors that are still pre-cutover.

    This is deliberately fail-closed: malformed/missing manifests, completed cutovers,
    non-exact mappings, or destinations outside skeleton/ai grant no exemption.
    """
    manifest = repo_root / "machine" / "ai_file_tree.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()

    if data.get("status") not in _AI_FILE_TREE_MIRROR_STATES:
        return ()

    prefixes: list[str] = []
    for item in data.get("mappings", ()):
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        destination = item.get("destination")
        parity_mode = item.get("parity_mode", "exact")
        if (
            source == "skeleton/api"
            and isinstance(destination, str)
            and destination == "skeleton/ai/runtime/api"
            and parity_mode == "exact"
        ):
            prefixes.append(destination.rstrip("/"))
    return tuple(sorted(set(prefixes)))


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    message: str

    def render(self, root: Path) -> str:
        try:
            display = self.path.relative_to(root)
        except ValueError:
            display = self.path
        return f"{display}:{self.line}: {self.message}"


def _python_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _imports_forbidden_kernel_dependency(module: str) -> bool:
    root = module.split(".", 1)[0]
    return root in _KERNEL_FORBIDDEN_ROOTS or module == "skeleton.api" or module.startswith("skeleton.api.")


def _imports_api(module: str, level: int = 0) -> bool:
    if module == "skeleton.api" or module.startswith("skeleton.api."):
        return True
    # Relative imports such as ``from ..api import routes`` should not bypass
    # the same boundary merely because they omit the absolute package prefix.
    return level > 0 and (module == "api" or module.startswith("api."))


def _matches_module(module: str, forbidden: str) -> bool:
    """Match one module namespace exactly or below it, never lookalike prefixes."""
    return module == forbidden or module.startswith(forbidden + ".")


def _production_rule_for(path: Path, repo_root: Path):
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        return None, None

    for rule in _PRODUCTION_RULES:
        root = rule["root"]
        if rel == root or rel.startswith(root + "/"):
            return rel, rule
    return rel, None


def _absolute_imports(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module]
    return []


def collect_violations(repo_root: Path = REPO_ROOT, *, require_roots: bool = False) -> list[Violation]:
    skeleton_root = repo_root / "skeleton"
    backend_root = repo_root / "backend"
    kernel_root = skeleton_root / "kernel"
    api_root = skeleton_root / "api"
    violations: list[Violation] = []
    staged_api_mirror_prefixes = _staged_api_mirror_prefixes(repo_root)

    if require_roots:
        for root_name in ("skeleton", "backend"):
            source_root = repo_root / root_name
            if not source_root.is_dir():
                violations.append(Violation(source_root, 1, "missing canonical source root"))

    source_roots = [root for root in (skeleton_root, backend_root) if root.is_dir()]
    for source_root in source_roots:
        for path in _python_files(source_root):
            rel, production_rule = _production_rule_for(path, repo_root)
            if rel is None:
                violations.append(Violation(path, 1, "source path is outside repository root"))
                continue

            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeError, SyntaxError) as exc:
                line = getattr(exc, "lineno", None) or 1
                violations.append(Violation(path, int(line), f"cannot validate Python module: {type(exc).__name__}"))
                continue

            in_skeleton = _is_under(path, skeleton_root)
            in_kernel = in_skeleton and _is_under(path, kernel_root)
            in_api = in_skeleton and _is_under(path, api_root)
            production_exempt = bool(
                production_rule
                and any(rel.startswith(prefix) for prefix in production_rule["excluded_prefixes"])
            )
            api_composition_root = rel in _API_COMPOSITION_ROOTS
            staged_api_mirror = any(
                rel == prefix or rel.startswith(prefix + "/")
                for prefix in staged_api_mirror_prefixes
            )

            for node in ast.walk(tree):
                imports: list[tuple[str, int]] = []
                if isinstance(node, ast.Import):
                    imports.extend((alias.name, 0) for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append((node.module or "", node.level))
                else:
                    continue

                for module, level in imports:
                    if in_kernel and level == 0 and _imports_forbidden_kernel_dependency(module):
                        violations.append(
                            Violation(
                                path,
                                node.lineno,
                                f"kernel must not import framework/I/O dependency {module!r}",
                            )
                        )

                    if (
                        in_skeleton
                        and not in_api
                        and not production_exempt
                        and not api_composition_root
                        and not staged_api_mirror
                        and _imports_api(module, level)
                    ):
                        violations.append(
                            Violation(
                                path,
                                node.lineno,
                                "domain/application code must not depend upward on skeleton.api",
                            )
                        )

                if production_rule and not production_exempt:
                    for module in _absolute_imports(node):
                        for forbidden in production_rule["forbidden_modules"]:
                            if _matches_module(module, forbidden):
                                violations.append(
                                    Violation(
                                        path,
                                        node.lineno,
                                        f"forbidden import {module!r} from {production_rule['root']} production code",
                                    )
                                )
                                break

    return violations


def main() -> int:
    violations = collect_violations(REPO_ROOT, require_roots=True)
    if not violations:
        print("architecture boundaries: ok")
        return 0

    print("architecture boundary violations:", file=sys.stderr)
    for violation in violations:
        print(f"- {violation.render(REPO_ROOT)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
