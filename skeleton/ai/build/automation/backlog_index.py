"""Deterministic static repository indexes for backlog automation."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import json
import re
from typing import Iterable

from .backlog_reader import Document

_JS_SYMBOL_PATTERNS = {
    ".js": re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\b"
        r"|^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b",
        re.MULTILINE,
    ),
    ".ts": re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\b"
        r"|^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b",
        re.MULTILINE,
    ),
    ".jsx": re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\b"
        r"|^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b",
        re.MULTILINE,
    ),
    ".tsx": re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\b"
        r"|^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b",
        re.MULTILINE,
    ),
}
_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)


@dataclass(frozen=True, slots=True)
class SymbolRecord:
    name: str
    path: str
    kind: str


@dataclass(frozen=True, slots=True)
class DependencyRecord:
    name: str
    path: str
    source: str


@dataclass(frozen=True, slots=True)
class ReferenceRecord:
    source: str
    target: str
    kind: str


@dataclass(frozen=True, slots=True)
class RepositoryIndex:
    files: tuple[Document, ...]
    symbols: tuple[SymbolRecord, ...] = field(default_factory=tuple)
    dependencies: tuple[DependencyRecord, ...] = field(default_factory=tuple)
    references: tuple[ReferenceRecord, ...] = field(default_factory=tuple)
    workflows: tuple[str, ...] = field(default_factory=tuple)
    tests: tuple[str, ...] = field(default_factory=tuple)

    def find_path(self, path: str) -> Document | None:
        return next((doc for doc in self.files if doc.path == path), None)

    def find_symbol(self, name: str) -> tuple[SymbolRecord, ...]:
        return tuple(symbol for symbol in self.symbols if symbol.name == name)

    def references_to(self, target: str) -> tuple[ReferenceRecord, ...]:
        return tuple(reference for reference in self.references if reference.target == target)


class RepositoryIndexBuilder:
    """Build static indexes from already-read bounded repository text."""

    def build(self, documents: Iterable[tuple[Document, str]]) -> RepositoryIndex:
        files: list[Document] = []
        symbols: list[SymbolRecord] = []
        dependencies: list[DependencyRecord] = []
        references: list[ReferenceRecord] = []
        workflows: list[str] = []
        tests: list[str] = []

        for document, content in documents:
            if not isinstance(content, str):
                raise TypeError("indexed content must be text")
            files.append(document)
            suffix = _suffix(document.path)

            if suffix == ".py":
                py_symbols, py_references = _python_records(document.path, content)
                symbols.extend(py_symbols)
                references.extend(py_references)
            elif suffix in _JS_SYMBOL_PATTERNS:
                symbols.extend(_javascript_symbols(document.path, content, suffix))
                references.extend(_javascript_references(document.path, content))

            if _is_dependency_file(document.path):
                dependencies.extend(_dependencies(document.path, content))
            if (
                document.path.lower().startswith(".github/workflows/")
                and suffix in {".yml", ".yaml"}
            ):
                workflows.append(document.path)
            if _is_test_file(document.path):
                tests.append(document.path)

        return RepositoryIndex(
            files=tuple(sorted(files, key=lambda doc: doc.path)),
            symbols=tuple(sorted(set(symbols), key=lambda item: (item.path, item.name, item.kind))),
            dependencies=tuple(
                sorted(set(dependencies), key=lambda item: (item.path, item.source, item.name))
            ),
            references=tuple(
                sorted(set(references), key=lambda item: (item.source, item.target, item.kind))
            ),
            workflows=tuple(sorted(set(workflows))),
            tests=tuple(sorted(set(tests))),
        )


def _python_records(
    path: str,
    content: str,
) -> tuple[list[SymbolRecord], list[ReferenceRecord]]:
    """Extract Python symbols/imports using the parser without executing code."""

    try:
        tree = ast.parse(content, filename=path)
    except (SyntaxError, ValueError, TypeError):
        return [], []

    symbols: list[SymbolRecord] = []
    references: list[ReferenceRecord] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append(SymbolRecord(node.name, path, "class"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(SymbolRecord(node.name, path, "function"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                references.append(ReferenceRecord(path, alias.name, "import"))
        elif isinstance(node, ast.ImportFrom):
            target = "." * node.level + (node.module or "")
            if target:
                references.append(ReferenceRecord(path, target, "import"))
    return symbols, references


def _javascript_symbols(path: str, content: str, suffix: str) -> list[SymbolRecord]:
    pattern = _JS_SYMBOL_PATTERNS[suffix]
    records: list[SymbolRecord] = []
    for match in pattern.finditer(content):
        if match.group(1):
            records.append(SymbolRecord(match.group(1), path, "function"))
        elif match.group(2):
            records.append(SymbolRecord(match.group(2), path, "class"))
    return records


def _javascript_references(path: str, content: str) -> list[ReferenceRecord]:
    pattern = re.compile(r"(?:from\s+|import\s+)[\"']([^\"']+)[\"']")
    return [
        ReferenceRecord(path, match.group(1), "import")
        for match in pattern.finditer(content)
    ]


def _suffix(path: str) -> str:
    lower = path.lower()
    for suffix in (
        ".py", ".js", ".ts", ".jsx", ".tsx", ".yaml", ".yml", ".json", ".toml"
    ):
        if lower.endswith(suffix):
            return suffix
    return ""


def _is_dependency_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return name in {
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    } or name.endswith("requirements.txt")


def _dependencies(path: str, content: str) -> list[DependencyRecord]:
    lower_path = path.lower()
    if lower_path.endswith("package.json"):
        return _package_json_dependencies(path, content)
    if lower_path.endswith("requirements.txt"):
        result: list[DependencyRecord] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "-")):
                continue
            name = re.split(r"[<>=!~;\[]", stripped, maxsplit=1)[0].strip()
            if name and "://" not in name and not name.startswith("git+"):
                result.append(DependencyRecord(name, path, "requirements"))
        return result
    return []


def _package_json_dependencies(path: str, content: str) -> list[DependencyRecord]:
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, dict):
        return []

    result: list[DependencyRecord] = []
    for section in _DEPENDENCY_SECTIONS:
        values = parsed.get(section)
        if not isinstance(values, dict):
            continue
        for name in values:
            if isinstance(name, str) and name:
                result.append(DependencyRecord(name, path, f"package-json:{section}"))
    return result


def _is_test_file(path: str) -> bool:
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{lower}/"
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
    )
