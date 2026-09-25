"""Read-only index over the pinned CC0 OpenAI Model Spec snapshot.

The Model Spec is research/reference input. It is deliberately not imported as
Skeleton runtime policy and cannot override Skeleton's own authority contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+\{#([^}]+)\})?\s*$")


@dataclass(frozen=True, slots=True)
class ModelSpecSection:
    level: int
    title: str
    anchor: str | None
    body: str
    start_line: int


class ModelSpecIndex:
    authoritative = False

    def __init__(self, snapshot_path: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[4]
        self.snapshot_path = snapshot_path or (
            root
            / "skeleton"
            / "ai"
            / "research"
            / "external"
            / "OpenAI"
            / "model_spec"
            / "model_spec.md.txt"
        )
        self._text: str | None = None
        self._sections: tuple[ModelSpecSection, ...] | None = None

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self.snapshot_path.read_text(encoding="utf-8")
        return self._text

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def sections(self) -> tuple[ModelSpecSection, ...]:
        if self._sections is not None:
            return self._sections
        lines = self.text.splitlines()
        headings: list[tuple[int, int, str, str | None]] = []
        for index, line in enumerate(lines):
            match = _HEADING.match(line)
            if match:
                headings.append(
                    (
                        index,
                        len(match.group(1)),
                        match.group(2).strip(),
                        match.group(3),
                    )
                )
        sections: list[ModelSpecSection] = []
        for offset, (line_index, level, title, anchor) in enumerate(headings):
            end = headings[offset + 1][0] if offset + 1 < len(headings) else len(lines)
            body = "\n".join(lines[line_index + 1 : end]).strip()
            sections.append(
                ModelSpecSection(
                    level=level,
                    title=title,
                    anchor=anchor,
                    body=body,
                    start_line=line_index + 1,
                )
            )
        self._sections = tuple(sections)
        return self._sections

    def find(self, query: str, *, limit: int = 20) -> tuple[ModelSpecSection, ...]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be non-empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be in [1, 100]")
        needle = query.casefold().strip()
        title_hits: list[ModelSpecSection] = []
        body_hits: list[ModelSpecSection] = []
        for section in self.sections():
            if needle in section.title.casefold():
                title_hits.append(section)
            elif needle in section.body.casefold():
                body_hits.append(section)
        return tuple((title_hits + body_hits)[:limit])


__all__ = ["ModelSpecIndex", "ModelSpecSection"]
