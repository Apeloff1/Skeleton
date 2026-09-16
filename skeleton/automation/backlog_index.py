"""Deterministic repository intelligence indexes for backlog automation.

Indexes are derived data: they never execute repository content and never grant
an LLM authority to change policy or tool permissions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

from .backlog_reader import Document

_SYMBOL_PATTERNS = {
    ".py": re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE),
    ".js": re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\b|^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b", re.MULTILINE),
    ".ts": re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\b|^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b", re.MULTILINE),
}

@dataclass(frozen=True)
class SymbolRecord:
    name: str
    path: str
    kind: str

@dataclass(frozen=True)
class DependencyRecord:
    name: str
    path: str
    source: str

@dataclass(frozen=True)
class RepositoryIndex:
    files: tuple[Document, ...]
    symbols: tuple[SymbolRecord, ...] = field(default_factory=tuple)
    dependencies: tuple[DependencyRecord, ...] = field(default_factory=tuple)
    workflows: tuple[str, ...] = field(default_factory=tuple)
    tests: tuple[str, ...] = field(default_factory=tuple)

    def find_path(self, path: str) -> Document | None:
        return next((doc for doc in self.files if doc.path == path), None)

    def find_symbol(self, name: str) -> tuple[SymbolRecord, ...]:
        return tuple(symbol for symbol in self.symbols if symbol.name == name)

class RepositoryIndexBuilder:
    """Build lightweight indexes from already-read, bounded repository files."""

    def build(self, documents: Iterable[tuple[Document, str]]) -> RepositoryIndex:
        files: list[Document] = []
        symbols: list[SymbolRecord] = []
        dependencies: list[DependencyRecord] = []
        workflows: list[str] = []
        tests: list[str] = []
        for document, content in documents:
            files.append(document)
            suffix = _suffix(document.path)
            pattern = _SYMBOL_PATTERNS.get(suffix)
            if pattern:
                for match in pattern.finditer(content):
                    name = next((group for group in match.groups() if group), None)
                    if name:
                        kind = "class" if "class" in match.group(0) else "function"
                        symbols.append(SymbolRecord(name, document.path, kind))
            if _is_dependency_file(document.path):
                dependencies.extend(_dependencies(document.path, content))
            if document.path.startswith(".github/workflows/") and suffix in {".yml", ".yaml"}:
                workflows.append(document.path)
            if _is_test_file(document.path):
                tests.append(document.path)
        return RepositoryIndex(tuple(files), tuple(symbols), tuple(dependencies), tuple(sorted(set(workflows))), tuple(sorted(set(tests))))

def _suffix(path: str) -> str:
    lower = path.lower()
    for suffix in (".py", ".js", ".ts", ".jsx", ".tsx", ".yaml", ".yml", ".json", ".toml"):
        if lower.endswith(suffix):
            return suffix
    return ""

def _is_dependency_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return name in {"pyproject.toml", "requirements.txt", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"} or name.endswith("requirements.txt")

def _dependencies(path: str, content: str) -> list[DependencyRecord]:
    result: list[DependencyRecord] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        if path.lower().endswith("requirements.txt"):
            name = re.split(r"[<>=!~;\[]", stripped, maxsplit=1)[0].strip()
            if name:
                result.append(DependencyRecord(name, path, "requirements"))
        elif path.lower().endswith("package.json"):
            match = re.search(r'"([^"/]+)"\s*:\s*"[^"\n]+"', stripped)
            if match and not match.group(1).startswith(("@types/", "name", "version")):
                result.append(DependencyRecord(match.group(1), path, "package-json"))
    return result

def _is_test_file(path: str) -> bool:
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    return "/tests/" in f"/{lower}/" or name.startswith("test_") or ".test." in name or ".spec." in name
