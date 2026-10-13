"""Bounded exact-index source reader for Jeeves app-aware coding workflows.

A host-supplied scoped atlas and read authorizer gate every request. The reader
rejects out-of-index paths, symlink traversal, stale filesystem metadata,
non-UTF8 data and oversized slices. No arbitrary filesystem path is readable
because a model named it, and no write action exists here.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable, Mapping

from .repository_file_atlas import JeevesRepositoryFileAtlas

MAX_LINES = 240
MAX_SLICE_BYTES = 64 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_LINE_NUMBER = 2_000_000


class JeevesSourceReadError(ValueError):
    """Source path, index identity, policy or content is not readable."""


def _sha(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise JeevesSourceReadError("expected index identity must be SHA-256")
    return value


class JeevesSourceReadGateway:
    """Host-authorized UTF-8 line slices from an existing file-atlas snapshot."""

    def __init__(
        self, atlas: JeevesRepositoryFileAtlas, *,
        authorize: Callable[..., bool],
    ) -> None:
        if not isinstance(atlas, JeevesRepositoryFileAtlas):
            raise TypeError("scoped repository atlas required")
        if not callable(authorize):
            raise TypeError("host source read authorizer required")
        self.atlas = atlas
        self.authorize = authorize

    def read(
        self, path: str, *,
        start_line: int, end_line: int,
        expected_index_sha256: str,
        context: Any,
    ) -> dict[str, Any]:
        if (type(start_line) is not int or type(end_line) is not int
                or not 1 <= start_line <= end_line <= MAX_LINE_NUMBER
                or end_line - start_line + 1 > MAX_LINES):
            raise JeevesSourceReadError("source range exceeds safe line budget")
        if (not isinstance(path, str) or not 1 <= len(path) <= 2048
                or path.startswith("/") or "\\" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            raise JeevesSourceReadError("source path must be canonical relative")
        expected = _sha(expected_index_sha256)
        meta = self.atlas.search(query="", limit=1, offset=0)
        if meta["index_sha256"] != expected:
            raise JeevesSourceReadError("source index changed since request planning")
        item = self.atlas.lookup(path)
        if item is None:
            raise JeevesSourceReadError("path is not in the host-governed atlas")
        if item.bytes > MAX_SOURCE_BYTES:
            raise JeevesSourceReadError("source file exceeds bounded read budget")
        intent = {
            "schema": "jeeves.source_read_intent.v1",
            "path": path, "start_line": start_line, "end_line": end_line,
            "index_sha256": expected,
        }
        digest = sha256(json.dumps(intent, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True).encode("utf-8")).hexdigest()
        if self.authorize("app.read_source", digest, context) is not True:
            raise JeevesSourceReadError("host denied exact source materialization")
        full = self.atlas.root / path
        parts = Path(path).parts
        if any((self.atlas.root / Path(*parts[:i])).is_symlink()
               for i in range(1, len(parts))):
            raise JeevesSourceReadError("symlink traversal denied")
        if not full.resolve().is_relative_to(self.atlas.root) or full.is_symlink():
            raise JeevesSourceReadError("indexed source escaped repository")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(full, flags)
        except OSError as exc:
            raise JeevesSourceReadError("indexed source is not readable") from exc
        try:
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode)
                        or info.st_size != item.bytes
                        or info.st_mtime_ns != item.modified_ns):
                    raise JeevesSourceReadError("source changed since atlas observation")
                selected: list[str] = []
                used = 0
                total_seen = 0
                has_more = False
                for number, raw in enumerate(stream, start=1):
                    total_seen = number
                    if number < start_line:
                        continue
                    if number > end_line:
                        has_more = True
                        break
                    used += len(raw)
                    if used > MAX_SLICE_BYTES:
                        raise JeevesSourceReadError("source slice exceeds 64 KiB")
                    try:
                        selected.append(raw.decode("utf-8", errors="strict"))
                    except UnicodeError as exc:
                        raise JeevesSourceReadError("indexed source is not UTF-8 text") from exc
        except BaseException:
            raise
        content = "".join(selected)
        return {
            "schema": "jeeves.source_slice.v1",
            "path": path,
            "owner_root": item.owner_root,
            "feature": item.feature,
            "start_line": start_line,
            "last_line": min(end_line, total_seen),
            "has_more": has_more,
            "content": content,
            "page_sha256": sha256(content.encode("utf-8")).hexdigest(),
            "content_sha256": item.content_sha256,
            "index_sha256": expected,
            "execution_authority": "none",
            "read_only": True,
        }


def register_source_read_tool(
    registry: Any, *, gateway: JeevesSourceReadGateway,
) -> str:
    """Register one READ_ONLY tool, preserving ToolExecutor grant control."""
    from skeleton.jeeves.agent.tools import (
        ArgumentRule, ToolRegistry, ToolSpec,
    )
    from skeleton.jeeves.agent.types import RiskTier
    if not isinstance(registry, ToolRegistry):
        raise TypeError("host ToolRegistry required")
    if not isinstance(gateway, JeevesSourceReadGateway):
        raise TypeError("host source gateway required")

    spec = ToolSpec(
        name="app.read_source",
        description="Read a host-authorized bounded UTF-8 slice of indexed app source.",
        risk=RiskTier.READ_ONLY,
        arguments=(
            ArgumentRule("path", "string", max_length=2048),
            ArgumentRule("start_line", "integer", minimum=1, maximum=MAX_LINE_NUMBER),
            ArgumentRule("end_line", "integer", minimum=1, maximum=MAX_LINE_NUMBER),
            ArgumentRule("expected_index_sha256", "string", max_length=64),
        ),
    )

    def _handle(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
        return gateway.read(
            args["path"], start_line=args["start_line"],
            end_line=args["end_line"],
            expected_index_sha256=args["expected_index_sha256"],
            context=context,
        )

    registry.register(spec, _handle)
    return spec.name


__all__ = [
    "JeevesSourceReadError", "JeevesSourceReadGateway",
    "register_source_read_tool",
]
