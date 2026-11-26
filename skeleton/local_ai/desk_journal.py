"""Append-only hash chain for desk turns.

Each line is one turn. The hash covers the previous hash, so a changed line
breaks every later check. The chain is rebuilt when the file is trimmed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

_GENESIS = "0" * 64
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_VERB = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_MAX_ANSWER = 16_000
_KEYS = ("answer", "hash", "i", "prev", "status", "verb")


class JournalRejected(ValueError):
    """A desk journal line is missing, tampered, or not a turn we can store."""


class DeskJournal:
    def __init__(self, path: str | os.PathLike[str], *, max_entries: int = 256) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or not 1 <= max_entries <= 256:
            raise JournalRejected("journal cap is invalid")
        self.path = Path(path)
        if self.path.is_symlink():
            raise JournalRejected("journal path is a symlink")
        self.max_entries = max_entries

    def entries(self) -> list[dict[str, object]]:
        rows = self._read()
        self._verify(rows)
        return rows

    def verify(self) -> None:
        self._verify(self._read())

    def append(self, verb: str, status: str, answer: str) -> dict[str, object]:
        if not isinstance(verb, str) or _VERB.fullmatch(verb) is None:
            raise JournalRejected("journal verb is invalid")
        if status not in {"ok", "refused"}:
            raise JournalRejected("journal status is invalid")
        if not isinstance(answer, str) or len(answer) > _MAX_ANSWER:
            raise JournalRejected("journal answer is invalid")
        rows = self._read()
        self._verify(rows)
        prev = str(rows[-1]["hash"]) if rows else _GENESIS
        number = int(rows[-1]["i"]) + 1 if rows else 1
        row = _row(number, verb, status, answer, prev)
        rows.append(row)
        if len(rows) > self.max_entries:
            rows = _rehash(rows[-self.max_entries :])
        self._write(rows)
        return row

    def _read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        if self.path.is_symlink() or not self.path.is_file():
            raise JournalRejected("chain broken")
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise JournalRejected("chain broken") from exc
        if not text:
            return []
        rows: list[dict[str, object]] = []
        for line in text.splitlines():
            if not line:
                raise JournalRejected("chain broken")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JournalRejected("chain broken") from exc
            rows.append(_checked(payload))
        return rows

    def _verify(self, rows: list[dict[str, object]]) -> None:
        prev = _GENESIS
        for index, row in enumerate(rows, start=1):
            if row["i"] != index or row["prev"] != prev:
                raise JournalRejected("chain broken")
            expected = _digest(index, str(row["verb"]), str(row["status"]), str(row["answer"]), prev)
            if row["hash"] != expected:
                raise JournalRejected("chain broken")
            prev = str(row["hash"])

    def _write(self, rows: list[dict[str, object]]) -> None:
        body = "".join(json.dumps(row, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
        parent = self.path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".journal.", suffix=".tmp", dir=parent)
        except OSError as exc:
            raise JournalRejected("journal could not be saved") from exc
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise JournalRejected("journal could not be saved") from exc


def _row(number: int, verb: str, status: str, answer: str, prev: str) -> dict[str, object]:
    return {
        "i": number,
        "verb": verb,
        "status": status,
        "answer": answer,
        "prev": prev,
        "hash": _digest(number, verb, status, answer, prev),
    }


def _digest(number: int, verb: str, status: str, answer: str, prev: str) -> str:
    body = json.dumps(
        {"answer": answer, "i": number, "prev": prev, "status": status, "verb": verb},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _rehash(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    prev = _GENESIS
    rebuilt: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        item = _row(index, str(row["verb"]), str(row["status"]), str(row["answer"]), prev)
        rebuilt.append(item)
        prev = str(item["hash"])
    return rebuilt


def _checked(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or tuple(sorted(payload)) != _KEYS:
        raise JournalRejected("chain broken")
    number = payload["i"]
    verb = payload["verb"]
    status = payload["status"]
    answer = payload["answer"]
    prev = payload["prev"]
    digest = payload["hash"]
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise JournalRejected("chain broken")
    if not isinstance(verb, str) or _VERB.fullmatch(verb) is None:
        raise JournalRejected("chain broken")
    if status not in {"ok", "refused"}:
        raise JournalRejected("chain broken")
    if not isinstance(answer, str) or len(answer) > _MAX_ANSWER:
        raise JournalRejected("chain broken")
    if not isinstance(prev, str) or _HEX.fullmatch(prev) is None:
        raise JournalRejected("chain broken")
    if not isinstance(digest, str) or _HEX.fullmatch(digest) is None:
        raise JournalRejected("chain broken")
    return payload
