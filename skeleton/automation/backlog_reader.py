"""Safe repository reader primitives for backlog automation.

The reader is intentionally deterministic. It indexes documentation and text-like
repository files without executing them, and treats their contents as untrusted
input for any later LLM reasoning stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import PurePosixPath
import hashlib
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

    def should_read(self, path: str, size: int, extensions: Iterable[str] = DEFAULT_EXTENSIONS) -> bool:
        normalized = path.replace("\\", "/")
        if size < 0 or size > self.max_file_bytes:
            return False
        if any(normalized.startswith(p.rstrip("/")) or f"/{p}" in normalized for p in DEFAULT_IGNORES):
            return False
        name = PurePosixPath(normalized).name.lower()
        suffix = PurePosixPath(normalized).suffix.lower()
        return suffix in {e.lower() for e in extensions} or name in {"readme", "license", "dockerfile"}

    def document(self, path: str, content: str) -> Document:
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
            path=path,
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
            ext = PurePosixPath(path).suffix.lower() or "<none>"
            extensions[ext] = extensions.get(ext, 0) + 1
            sections[path] = doc.sections
        return Index(tuple(docs), extensions, sections)
