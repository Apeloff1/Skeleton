#!/usr/bin/env python3
"""Fail closed on high-risk Skeleton package boundary violations.

The first enforcement slice is intentionally small: keep the kernel dependency-free
and prevent domain/application code from depending upward on the HTTP adapter.
See docs/CANONICAL_MODULE_BOUNDARIES.md for the full ownership contract.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SKELETON_ROOT = REPO_ROOT / "skeleton"

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


def collect_violations(repo_root: Path = REPO_ROOT) -> list[Violation]:
    skeleton_root = repo_root / "skeleton"
    kernel_root = skeleton_root / "kernel"
    api_root = skeleton_root / "api"
    violations: list[Violation] = []

    for path in _python_files(skeleton_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            line = getattr(exc, "lineno", None) or 1
            violations.append(Violation(path, int(line), f"cannot validate Python module: {type(exc).__name__}"))
            continue

        in_kernel = _is_under(path, kernel_root)
        in_api = _is_under(path, api_root)
        cli_entry = path == skeleton_root / "__main__.py"

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

                if not in_api and not cli_entry and _imports_api(module, level):
                    violations.append(
                        Violation(
                            path,
                            node.lineno,
                            "domain/application code must not depend upward on skeleton.api",
                        )
                    )

    return violations


def main() -> int:
    violations = collect_violations()
    if not violations:
        print("architecture boundaries: ok")
        return 0

    print("architecture boundary violations:", file=sys.stderr)
    for violation in violations:
        print(f"- {violation.render(REPO_ROOT)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
