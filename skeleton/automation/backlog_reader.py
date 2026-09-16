"""Safe repository reader primitives for backlog automation.

The reader is deterministic: it indexes text-like repository files without
executing them and treats contents as untrusted input for later reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
import hashlib
from pathlib import PurePosixPath
from typing import Iterable

DEFAULT_EXTENSIONS = frozenset({
    ".md", ".mdx", ".rst", ".txt", ".yaml", ".yml", ".json", ".toml",
    ".ini", ".cfg", ".py", ".js", ".jsx", ".ts", ".tsx", ".sh", ".ps1",
    ".dockerfile", ".xml", ".html", ".css", ".sql",
})
DEFAULT_IGNORES = (
    ".git/", "node_modules/", ".venv/", "venv/", "dist/", "build/",
    "coverage/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
    "__pycache__/", "*.pyc", "*.pyo", "*.zip", "*.tar", "*.gz",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.pdf",
)


@dataclass(frozen=True)
class Document:
    path: str
    sha256: str
    size: int
    lines: int
    sections: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Index:
    documents: tuple[Document, ...]
    by_extension: dict[str, int]
    sections: dict[str, tuple[str, ...]]

    @property
    def count(self) -> int:
        return len(self.documents)


class RepositoryReader:
    """Bounded local reader; never executes discovered content."""

    def __init__(self, *, max_file_bytes: int = 1_000_000, max_files: int = 20_000) -> None:
        if max_file_bytes <= 0 or max_files <= 0:
            raise ValueError("reader limits must be positive")
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files

    @staticmethod
    def _normalized_path(path: str) -> str:
        normalized = path.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError("path must be repository-relative and normalized")
        return pure.as_posix()

    def should_read(self, path: str, size: int, extensions: Iterable[str] = DEFAULT_EXTENSIONS) -> bool:
        normalized = self._normalized_path(path)
        if size < 0 or size > self.max_file_bytes:
            return False
        name = PurePosixPath(normalized).name.lower()
        if any(
            normalized == ignored.rstrip("/") or normalized.startswith(ignored)
            for ignored in DEFAULT_IGNORES
            if ignored.endswith("/")
        ):
            return False
        if any(fnmatch(name, pattern.lower()) for pattern in DEFAULT_IGNORES if not pattern.endswith("/")):
            return False
        suffix = PurePosixPath(normalized).suffix.lower()
        return suffix in {e.lower() for e in extensions} or name in {"readme", "license", "dockerfile"}

    def document(self, path: str, content: str) -> Document:
        normalized = self._normalized_path(path)
        encoded = content.encode("utf-8", errors="replace")
        if len(encoded) > self.max_file_bytes:
            raise ValueError("document exceeds configured size limit")
        sections: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()
                if heading:
                    sections.append(heading[:200])
        return Document(
            path=normalized,
            sha256=hashlib.sha256(encoded).hexdigest(),
            size=len(encoded),
            lines=len(content.splitlines()),
            sections=tuple(sections),
        )

    def index(self, files: Iterable[tuple[str, str, int]]) -> Index:
        docs: list[Document] = []
        extensions: dict[str, int] = {}
        sections: dict[str, tuple[str, ...]] = {}
        for path, content, size in files:
            if len(docs) >= self.max_files:
                break
            if not self.should_read(path, size):
                continue
            doc = self.document(path, content)
            docs.append(doc)
            ext = PurePosixPath(doc.path).suffix.lower() or "<none>"
            extensions[ext] = extensions.get(ext, 0) + 1
            sections[doc.path] = doc.sections
        return Index(tuple(docs), extensions, sections)
