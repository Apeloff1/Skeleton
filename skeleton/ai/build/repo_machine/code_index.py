"""Cross-language static repository symbol/reference extraction.

The index is intentionally heuristic for non-Python languages. Records include
confidence so callers cannot mistake regex inference for parser certainty.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Iterable


class CodeIndexError(RuntimeError):
    """Raised when source text cannot be indexed without ambiguity."""


def _repo_path(value: str) -> str:
    text = str(value)
    if not text or "\x00" in text or "\\" in text:
        raise CodeIndexError("path must be non-empty canonical POSIX text")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise CodeIndexError(f"unsafe repository path: {value!r}")
    if pure.as_posix() != text:
        raise CodeIndexError(f"non-canonical repository path: {value!r}")
    return text


@dataclass(frozen=True, slots=True)
class CodeSymbol:
    name: str
    path: str
    kind: str
    language: str
    confidence: str


@dataclass(frozen=True, slots=True)
class CodeReference:
    source: str
    target: str
    kind: str
    language: str
    confidence: str


_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
}

_SYMBOL_PATTERNS = {
    "javascript": re.compile(
        r"^\s*(?:export\s+)?(?:(?:async\s+)?function|class)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    ),
    "typescript": re.compile(
        r"^\s*(?:export\s+)?(?:(?:async\s+)?function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    ),
    "go": re.compile(r"^\s*(?:func|type)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", re.MULTILINE),
    "rust": re.compile(
        r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:fn|struct|enum|trait|type|mod)\s+([A-Za-z_]\w*)",
        re.MULTILINE,
    ),
    "java": re.compile(
        r"^\s*(?:public|protected|private|abstract|final|static|sealed|non-sealed|\s)*\s*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)",
        re.MULTILINE,
    ),
    "kotlin": re.compile(
        r"^\s*(?:public|private|internal|protected|data|sealed|open|abstract|\s)*\s*(?:class|interface|object|fun|typealias)\s+([A-Za-z_]\w*)",
        re.MULTILINE,
    ),
    "c": re.compile(
        r"^\s*(?:[A-Za-z_]\w*[\s\*]+)+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{",
        re.MULTILINE,
    ),
    "cpp": re.compile(
        r"^\s*(?:(?:class|struct|enum)\s+([A-Za-z_]\w*)|(?:[A-Za-z_:<>~]\w*[\s\*&:<>~]+)+([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:const\s*)?\{)",
        re.MULTILINE,
    ),
}

_REFERENCE_PATTERNS = {
    "javascript": re.compile(r"(?:from\s+|import\s*\(?\s*)[\"']([^\"']+)[\"']"),
    "typescript": re.compile(r"(?:from\s+|import\s*\(?\s*)[\"']([^\"']+)[\"']"),
    "go": re.compile(r"^\s*import\s+(?:[A-Za-z_]\w*\s+)?[\"']([^\"']+)[\"']", re.MULTILINE),
    "rust": re.compile(r"^\s*(?:use|mod)\s+([^;{]+)", re.MULTILINE),
    "java": re.compile(r"^\s*import\s+(?:static\s+)?([^;]+);", re.MULTILINE),
    "kotlin": re.compile(r"^\s*import\s+([^\s;]+)", re.MULTILINE),
    "c": re.compile(r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", re.MULTILINE),
    "cpp": re.compile(r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", re.MULTILINE),
}


def language_for_path(path: str) -> str | None:
    normalized = _repo_path(path)
    return _LANGUAGE_BY_SUFFIX.get(PurePosixPath(normalized).suffix.lower())


def extract_records(path: str, content: str) -> tuple[tuple[CodeSymbol, ...], tuple[CodeReference, ...]]:
    normalized = _repo_path(path)
    if not isinstance(content, str):
        raise TypeError("content must be text")
    if len(content) > 5_000_000:
        raise CodeIndexError("source text exceeds 5,000,000 character indexing bound")
    language = language_for_path(normalized)
    if language is None:
        return (), ()
    if language == "python":
        return _python_records(normalized, content)

    symbols: set[CodeSymbol] = set()
    references: set[CodeReference] = set()
    pattern = _SYMBOL_PATTERNS.get(language)
    if pattern is not None:
        for match in pattern.finditer(content):
            name = next((group for group in match.groups() if group), None)
            if name:
                symbols.add(CodeSymbol(name, normalized, "symbol", language, "heuristic"))
    ref_pattern = _REFERENCE_PATTERNS.get(language)
    if ref_pattern is not None:
        for match in ref_pattern.finditer(content):
            target = match.group(1).strip()
            if target:
                references.add(CodeReference(normalized, target, "import", language, "heuristic"))
    return (
        tuple(sorted(symbols, key=lambda item: (item.path, item.name))),
        tuple(sorted(references, key=lambda item: (item.source, item.target))),
    )


def _python_records(path: str, content: str) -> tuple[tuple[CodeSymbol, ...], tuple[CodeReference, ...]]:
    try:
        tree = ast.parse(content, filename=path)
    except (SyntaxError, ValueError, TypeError) as exc:
        raise CodeIndexError(f"cannot parse Python source {path}: {exc}") from exc
    symbols: set[CodeSymbol] = set()
    references: set[CodeReference] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.add(CodeSymbol(node.name, path, "class", "python", "parser"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.add(CodeSymbol(node.name, path, "function", "python", "parser"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                references.add(CodeReference(path, alias.name, "import", "python", "parser"))
        elif isinstance(node, ast.ImportFrom):
            target = "." * node.level + (node.module or "")
            if target:
                references.add(CodeReference(path, target, "import", "python", "parser"))
    return (
        tuple(sorted(symbols, key=lambda item: (item.path, item.name, item.kind))),
        tuple(sorted(references, key=lambda item: (item.source, item.target))),
    )


def build_language_inventory(documents: Iterable[tuple[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    seen_paths: set[str] = set()
    for path, content in documents:
        normalized = _repo_path(path)
        if normalized in seen_paths:
            raise CodeIndexError(f"duplicate source path in index input: {normalized}")
        seen_paths.add(normalized)
        language = language_for_path(normalized)
        if language is None:
            continue
        symbols, _ = extract_records(normalized, content)
        counts[language] = counts.get(language, 0) + len(symbols)
    return dict(sorted(counts.items()))


__all__ = [
    "CodeIndexError",
    "CodeReference",
    "CodeSymbol",
    "build_language_inventory",
    "extract_records",
    "language_for_path",
]
