"""Deterministic, bounded, cross-language source navigation for Jeeves.

This indexes real paths from the canonical appwide inventory. It searches
checked-out UTF-8 source bytes without imports, evaluation, indexing private
files or loading unbounded source trees into a model context.
"""
from __future__ import annotations

from bisect import bisect_right, bisect_left
from hashlib import sha256
from typing import Any

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, _relative, digest, PRIVATE,
)

SCHEMA = "skeleton.ai.jeeves_code_navigator.v1"
MAX_LOOKUPS = 72
MAX_FILE_BYTES = 128_000
MAX_SEARCH_BYTES = 2_000_000
MAX_LINES = 80
MAX_SOURCE_LINE = 600
MAX_MATCHES = 48
MAX_PER_FILE = 6
MAX_QUERY = 128
MAX_ROOT = 256
MAX_SCAN_RESULTS = 150


def _int(value: Any, label: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise JeevesAppwideError("invalid bounded " + label)
    return value


def _excerpt_line(line: str, *, index: int = 0) -> tuple[str, bool]:
    """Preserve text around an occurrence while bounding huge source lines."""
    if len(line) <= MAX_SOURCE_LINE:
        return line, False
    width = MAX_SOURCE_LINE - 1
    begin = max(0, min(index - width // 3, len(line) - width))
    end = min(len(line), begin + width)
    return line[begin:end], True


def _normalize_prefix(value: Any) -> str:
    if value is None or value == "":
        return ""
    if type(value) is not str or len(value) > MAX_ROOT:
        raise JeevesAppwideError("invalid bounded search prefix")
    prefix = _relative(value.rstrip("/"))
    if PRIVATE.search(prefix):
        raise JeevesAppwideError("private search root rejected")
    return prefix + "/"


class JeevesCodeNavigator:
    """Page through a fixed source snapshot; never index invisible files."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("reviewed source inventory required")
        inventory._require_scanned()
        self.inv = inventory
        self.paths = list(inventory._files)

    def _snapshot(self, expected):
        if expected is not None and expected != self.inv._digest:
            raise JeevesAppwideError("stale source navigation snapshot")

    def search(
        self, *, query, prefix="", start_after=None, max_files=48,
        max_matches=32, case_sensitive=False, expected_snapshot=None,
    ):
        self._snapshot(expected_snapshot)
        if (type(query) is not str or
                not 2 <= len(query) <= MAX_QUERY or
                "\x00" in query or "\r" in query or "\n" in query):
            raise JeevesAppwideError("bounded literal source query required")
        if type(case_sensitive) is not bool:
            raise JeevesAppwideError("case sensitivity must be boolean")
        _int(max_files, "file count", 1, MAX_LOOKUPS)
        _int(max_matches, "match count", 1, MAX_MATCHES)
        root = _normalize_prefix(prefix)
        if start_after is not None:
            cursor = _relative(start_after)
            if PRIVATE.search(cursor):
                raise JeevesAppwideError("private cursor forbidden")
            if root and not cursor.startswith(root):
                raise JeevesAppwideError("cursor outside selected source root")
            index = bisect_right(self.paths, cursor)
        else:
            index = bisect_left(self.paths, root)
        found = []
        inspected = []
        bytes_read = 0
        restricted = 0
        nontext = 0
        oversize = 0
        content_missing = 0
        files_examined = 0
        last = None
        needle = query if case_sensitive else query.casefold()
        while index < len(self.paths) and files_examined < max_files:
            path = self.paths[index]
            if root and not path.startswith(root):
                break
            entry = self.inv._files[path]
            if (entry.readable and entry.kind in ("source", "text") and
                    entry.bytes <= MAX_FILE_BYTES and
                    entry.bytes + bytes_read > MAX_SEARCH_BYTES):
                break
            index += 1
            last = path
            files_examined += 1
            if not entry.readable:
                restricted += 1
                continue
            if entry.kind not in ("source", "text"):
                nontext += 1
                continue
            if entry.bytes > MAX_FILE_BYTES:
                oversize += 1
                continue
            try:
                content = self.inv._safe_file(path, max_size=MAX_FILE_BYTES)
            except JeevesAppwideError:
                content_missing += 1
                continue
            bytes_read += len(content.encode("utf-8"))
            source_hash = sha256(content.encode("utf-8")).hexdigest()
            lines = content.splitlines()
            hits = []
            for lineno, line in enumerate(lines, 1):
                target = line if case_sensitive else line.casefold()
                pos = target.find(needle)
                if pos < 0:
                    continue
                excerpt, clipped = _excerpt_line(line, index=pos)
                hits.append({
                    "line": lineno, "excerpt": excerpt,
                    "excerpt_clipped": clipped,
                    "text_only_not_a_callable_reference": True,
                })
                if len(hits) >= MAX_PER_FILE:
                    break
            if hits:
                found.append({
                    "path": path,
                    "source_sha256": source_hash,
                    "source_bytes": entry.bytes,
                    "matches": hits,
                    "per_file_matches_capped": len(hits) == MAX_PER_FILE,
                })
                if len(found) >= max_matches:
                    break
            inspected.append(path)
        remaining = index < len(self.paths) and (
            not root or self.paths[index].startswith(root)
        )
        # Do not silently advance when a byte-limit stop happened before
        # the next file: last is the exact previous visited path.
        body = {
            "schema": SCHEMA + ".search",
            "inventory_snapshot": self.inv._digest,
            "prefix": root,
            "query": query,
            "case_sensitive": case_sensitive,
            "start_after": start_after,
            "next_after": last if remaining else None,
            "files_examined": files_examined,
            "source_bytes_inspected": bytes_read,
            "matched_file_count": len(found),
            "matched_line_samples": sum(len(f["matches"]) for f in found),
            "skipped_restricted": restricted,
            "skipped_nontext": nontext,
            "skipped_oversized": oversize,
            "skipped_changed_or_unreadable": content_missing,
            "matches": found,
            "truncated_or_page_incomplete": remaining,
            "more_matches_may_exist": remaining or bool(oversize or content_missing),
            "literal_casefold_not_semantic_code_search": True,
            "all_source_bytes_scoped_and_non_executing": True,
        }
        return {**body, "digest": digest(body)}

    def snippet(
        self, *, path, start_line=1, line_count=24, expected_sha256=None,
        expected_snapshot=None,
    ):
        self._snapshot(expected_snapshot)
        path = _relative(path)
        if PRIVATE.search(path):
            raise JeevesAppwideError("private source snippet forbidden")
        _int(start_line, "source starting line", 1, 50_000_000)
        _int(line_count, "source line count", 1, MAX_LINES)
        record = self.inv._files.get(path)
        if (record is None or not record.readable or
                record.kind not in ("source", "text")):
            raise JeevesAppwideError("source not available for bounded paging")
        if record.bytes > MAX_FILE_BYTES:
            raise JeevesAppwideError("large source requires a specialized reader")
        content = self.inv._safe_file(path, max_size=MAX_FILE_BYTES)
        checksum = sha256(content.encode("utf-8")).hexdigest()
        if expected_sha256 is not None and expected_sha256 != checksum:
            raise JeevesAppwideError("source changed since selected context")
        lines = content.splitlines()
        start = start_line - 1
        if start > len(lines):
            raise JeevesAppwideError("requested line lies beyond source")
        selection = []
        for offset, line in enumerate(lines[start:start + line_count], start_line):
            excerpt, clipped = _excerpt_line(line)
            selection.append({
                "line": offset, "text": excerpt,
                "line_truncated": clipped,
            })
        end = start + len(selection)
        body = {
            "schema": SCHEMA + ".snippet",
            "path": path,
            "inventory_snapshot": self.inv._digest,
            "source_sha256": checksum,
            "source_bytes": record.bytes,
            "total_lines": len(lines),
            "start_line": start_line,
            "returned_lines": len(selection),
            "next_line": end + 1 if end < len(lines) else None,
            "lines": selection,
            "bounded_context_no_source_execution": True,
            "exact_source_digest_requires_freshness_on_edit": True,
        }
        return {**body, "digest": digest(body)}
