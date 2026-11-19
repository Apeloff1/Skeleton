"""File-backed markdown memory. No model is bound."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_MAX_FACT_CHARS = 500
_MAX_FILE_BYTES = 64 * 1024
_SECRET = re.compile(r"(?i)\b(api[_-]?key|secret|password|token|bearer)\b\s*[:=]")
_NEGATION = re.compile(r"(?i)^not\s+(.+)$")


class MemoryRejected(ValueError):
    """A fact or memory file update was refused."""


def _render(facts: list[str]) -> str:
    lines = ["# Memory", ""]
    lines.extend(f"- {fact}" for fact in facts)
    return "\n".join(lines) + "\n"


def _parse(text: str) -> list[str]:
    facts: list[str] = []
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        fact = line[2:]
        if fact:
            facts.append(fact)
    return facts


def _negation_target(fact: str) -> str | None:
    match = _NEGATION.fullmatch(fact)
    if match is None:
        return None
    target = match.group(1).strip()
    return target or None


class MemoryBook:
    """Markdown bullets under ``# Memory``, stored by an atomic replace."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def remember(self, fact: str) -> None:
        cleaned = _validate_fact(fact)
        facts = self._load()
        target = _negation_target(cleaned)
        if target is not None:
            folded_target = target.casefold()
            facts = [item for item in facts if item.casefold() != folded_target]
        folded = cleaned.casefold()
        if any(item.casefold() == folded for item in facts):
            if facts != self._load():
                self._save(facts)
            return
        facts.append(cleaned)
        self._save(facts)

    def replace(self, old: str, new: str) -> None:
        old_clean = _validate_fact(old)
        new_clean = _validate_fact(new)
        facts = self._load()
        folded_old = old_clean.casefold()
        if not any(item.casefold() == folded_old for item in facts):
            raise MemoryRejected("no matching fact")
        remaining = [item for item in facts if item.casefold() != folded_old]
        target = _negation_target(new_clean)
        if target is not None:
            folded_target = target.casefold()
            remaining = [item for item in remaining if item.casefold() != folded_target]
        folded_new = new_clean.casefold()
        if any(item.casefold() == folded_new for item in remaining):
            self._save(remaining)
            return
        remaining.append(new_clean)
        self._save(remaining)

    def forget(self, fact: str) -> None:
        cleaned = _validate_fact(fact)
        facts = self._load()
        folded = cleaned.casefold()
        kept = [item for item in facts if item.casefold() != folded]
        if len(kept) == len(facts):
            raise MemoryRejected("no matching fact")
        self._save(kept)

    def search(self, query: str) -> list[str]:
        if not isinstance(query, str):
            raise MemoryRejected("query must be a string")
        terms = [term.casefold() for term in query.split() if term]
        facts = self._load()
        if not terms:
            return []
        return [fact for fact in facts if all(term in fact.casefold() for term in terms)]

    def render(self) -> str:
        return _render(self._load())

    def facts(self) -> list[str]:
        return list(self._load())

    def replace_all(self, facts: list[str]) -> None:
        """Replace the book with an already-valid snapshot.

        Used to roll a desk program back after a later step fails.
        """
        if not isinstance(facts, list):
            raise MemoryRejected("facts must be a list")
        cleaned = [_validate_fact(fact) for fact in facts]
        self._save(cleaned)

    def _load(self) -> list[str]:
        if not self.path.exists():
            return []
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MemoryRejected("memory file could not be read") from exc
        except UnicodeDecodeError as exc:
            raise MemoryRejected("memory file must be utf-8") from exc
        return _parse(text)

    def _save(self, facts: list[str]) -> None:
        payload = _render(facts).encode("utf-8")
        if len(payload) > _MAX_FILE_BYTES:
            raise MemoryRejected("memory file exceeds 64 KiB")
        parent = self.path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".memory.", suffix=".tmp", dir=parent)
        except OSError as exc:
            raise MemoryRejected("memory file could not be saved") from exc
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise MemoryRejected("memory file could not be saved") from exc


def screen_fact(fact: object) -> str:
    """Return the stored form of a fact, or raise MemoryRejected."""
    return _validate_fact(fact)


def _validate_fact(fact: object) -> str:
    if not isinstance(fact, str):
        raise MemoryRejected("fact must be a string")
    if len(fact) > _MAX_FACT_CHARS:
        raise MemoryRejected("fact exceeds 500 characters")
    cleaned = fact.strip()
    if not cleaned:
        raise MemoryRejected("fact is empty")
    if len(cleaned) > _MAX_FACT_CHARS:
        raise MemoryRejected("fact exceeds 500 characters")
    if any(ord(ch) < 32 and ch != "\t" for ch in cleaned):
        raise MemoryRejected("fact contains a control character")
    if _SECRET.search(fact) or _SECRET.search(cleaned):
        raise MemoryRejected("fact contains a secret")
    return cleaned
