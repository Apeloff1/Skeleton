"""Deterministic repository indexing for autonomous feature builds.

Only immutable HEAD content is read. The index gives the model an architectural
map without dumping an entire repository into provider context. Selection is
lexical and deterministic; model output never controls which commands execute.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
import subprocess
from typing import Iterable, Sequence

from .advanced_bots import BLOCKED_PREFIXES
from .build_contracts import BuildBudget
from .free_model import redact_secrets
from .supervisor_runtime import canonical_json


DEFAULT_ROOTS = (
    "skeleton",
    "tests",
    "docs",
    "backend",
    "frontend",
    "core",
)
TEXT_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",
        ".md",
        ".mdx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".java",
        ".kt",
        ".kts",
        ".go",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".css",
        ".scss",
        ".html",
        ".sh",
        ".sql",
        ".graphql",
    }
)
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_./:-]{2,}")
MAX_TREE_PATHS = 20_000
MAX_ENTRY_BYTES = 500_000
MAX_SYMBOLS = 128


class BuildIndexError(RuntimeError):
    """Repository indexing failed closed."""


def _git_output(args: list[str], *, timeout: int = 30) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise BuildIndexError(
            "unable to inspect immutable repository state"
        ) from exc


def _safe_index_path(path: str) -> bool:
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or "//" in path
    ):
        return False
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    if any(path.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        return False
    return True


def _suffix(path: str) -> str:
    return PurePosixPath(path).suffix.casefold()


def _tokens(text: str) -> set[str]:
    return {
        match.group(0).casefold()
        for match in TOKEN_RE.finditer(text or "")
    }


def _symbol_names(path: str, content: str) -> tuple[str, ...]:
    if not path.endswith((".py", ".pyi")):
        return ()
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError:
        return ()
    names: list[str] = []
    for node in tree.body:
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            names.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            for target in targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        if len(names) >= MAX_SYMBOLS:
            break
    return tuple(names)


@dataclass(frozen=True, slots=True)
class IndexEntry:
    path: str
    bytes: int
    lines: int
    digest: str
    symbols: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "bytes": self.bytes,
            "lines": self.lines,
            "digest": self.digest,
            "symbols": list(self.symbols),
        }


@dataclass(frozen=True, slots=True)
class ContextFile:
    path: str
    content: str
    score: int
    digest: str
    truncated: bool

    def as_prompt_block(self) -> str:
        marker = " [TRUNCATED]" if self.truncated else ""
        return (
            f"\n--- {self.path}{marker} "
            f"sha256={self.digest} score={self.score} ---\n"
            f"{self.content}\n"
        )


@dataclass(frozen=True, slots=True)
class RepositoryIndex:
    head_sha: str
    entries: tuple[IndexEntry, ...]
    directory_counts: tuple[tuple[str, int], ...]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "head_sha": self.head_sha,
                    "entries": [item.as_dict() for item in self.entries],
                    "directory_counts": self.directory_counts,
                }
            )
        ).hexdigest()

    @classmethod
    def capture(
        cls,
        *,
        roots: Sequence[str] = DEFAULT_ROOTS,
    ) -> "RepositoryIndex":
        head = _git_output(["rev-parse", "HEAD"]).strip()
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            raise BuildIndexError("invalid immutable HEAD identity")

        raw = _git_output(
            ["ls-tree", "-r", "--long", "HEAD", "--", *roots],
            timeout=45,
        )
        entries: list[IndexEntry] = []
        directories: dict[str, int] = {}

        for line in raw.splitlines():
            if len(entries) >= MAX_TREE_PATHS:
                break
            try:
                meta, path = line.split("\t", 1)
                left = meta.split()
                if len(left) != 4:
                    continue
                _mode, kind, digest, size_text = left
                if kind != "blob":
                    continue
                size = int(size_text)
            except (ValueError, TypeError):
                continue
            if not _safe_index_path(path):
                continue
            if _suffix(path) not in TEXT_EXTENSIONS:
                continue
            if size < 0 or size > MAX_ENTRY_BYTES:
                continue

            directory = path.split("/", 1)[0]
            directories[directory] = directories.get(directory, 0) + 1
            entries.append(
                IndexEntry(
                    path=path,
                    bytes=size,
                    lines=0,
                    digest=digest,
                    symbols=(),
                )
            )

        entries.sort(key=lambda item: item.path)
        return cls(
            head_sha=head,
            entries=tuple(entries),
            directory_counts=tuple(sorted(directories.items())),
        )

    def paths(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.entries)

    def read_text(
        self,
        path: str,
        *,
        max_bytes: int | None = None,
    ) -> str:
        """Read one admitted immutable HEAD text path without model control."""
        known = {item.path for item in self.entries}
        if path not in known:
            raise BuildIndexError(
                "requested path is outside captured repository index"
            )
        content = _git_output(
            ["show", f"HEAD:{path}"],
            timeout=20,
        )
        size = len(content.encode("utf-8"))
        if max_bytes is not None:
            if (
                isinstance(max_bytes, bool)
                or not isinstance(max_bytes, int)
                or max_bytes < 1
            ):
                raise BuildIndexError(
                    "invalid immutable read byte budget"
                )
            if size > max_bytes:
                raise BuildIndexError(
                    "immutable source exceeds requested read budget"
                )
        return content

    def render_manifest(self, *, max_entries: int = 1200) -> str:
        rows = [
            {
                "path": item.path,
                "bytes": item.bytes,
                "digest": item.digest,
            }
            for item in self.entries[:max_entries]
        ]
        payload = {
            "head_sha": self.head_sha,
            "fingerprint": self.fingerprint,
            "directories": dict(self.directory_counts),
            "entries": rows,
            "truncated": len(self.entries) > max_entries,
        }
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )

    def select_context(
        self,
        *,
        task_text: str,
        plan_text: str,
        budget: BuildBudget,
        planned_paths: Iterable[str] = (),
        per_file_bytes: int = 12_000,
    ) -> tuple[ContextFile, ...]:
        task_tokens = _tokens(task_text)
        plan_tokens = _tokens(plan_text)
        requested = set(planned_paths)
        scored: list[tuple[int, str]] = []

        for entry in self.entries:
            path_tokens = _tokens(entry.path.replace("/", " "))
            score = 0
            score += 18 * len(path_tokens & task_tokens)
            score += 9 * len(path_tokens & plan_tokens)
            if entry.path in requested:
                score += 10_000
            name = PurePosixPath(entry.path).name.casefold()
            if any(token in name for token in task_tokens):
                score += 25
            if entry.path.endswith(
                (
                    "README.md",
                    "pyproject.toml",
                    "package.json",
                    "Cargo.toml",
                    "go.mod",
                    "build.gradle",
                    "settings.gradle",
                )
            ):
                score += 3
            if score > 0:
                scored.append((score, entry.path))

        scored.sort(key=lambda item: (-item[0], item[1]))
        result: list[ContextFile] = []
        total = 0
        for score, path in scored:
            try:
                content = _git_output(
                    ["show", f"HEAD:{path}"],
                    timeout=15,
                )
            except BuildIndexError:
                continue
            raw = content.encode("utf-8", errors="ignore")
            truncated = len(raw) > per_file_bytes
            clipped = raw[:per_file_bytes].decode(
                "utf-8",
                errors="ignore",
            )
            clipped = redact_secrets(clipped)
            block_size = (
                len(clipped.encode("utf-8"))
                + len(path.encode("utf-8"))
                + 160
            )
            if total + block_size > budget.max_context_bytes:
                break
            digest = hashlib.sha256(raw).hexdigest()
            result.append(
                ContextFile(
                    path=path,
                    content=clipped,
                    score=score,
                    digest=digest,
                    truncated=truncated,
                )
            )
            total += block_size
        return tuple(result)


def enrich_entries(
    index: RepositoryIndex,
    paths: Iterable[str],
) -> tuple[IndexEntry, ...]:
    """Read a small exact subset and attach line/symbol metadata."""
    wanted = set(paths)
    result = []
    by_path = {item.path: item for item in index.entries}
    for path in sorted(wanted):
        base = by_path.get(path)
        if base is None:
            continue
        try:
            content = _git_output(["show", f"HEAD:{path}"])
        except BuildIndexError:
            continue
        result.append(
            IndexEntry(
                path=path,
                bytes=len(content.encode("utf-8")),
                lines=len(content.splitlines()),
                digest=hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest(),
                symbols=_symbol_names(path, content),
            )
        )
    return tuple(result)


def render_context(files: Sequence[ContextFile]) -> str:
    return "".join(item.as_prompt_block() for item in files)
