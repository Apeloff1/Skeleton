"""Bounded TSV retrieval evidence with no spreadsheet execution or link fanout."""
from __future__ import annotations

import csv
import io

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

TSV_MEDIA_TYPES = frozenset({"text/tab-separated-values", "application/tsv"})


def extract_tsv(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        rows = csv.reader(io.StringIO(raw, newline=""), delimiter="\t", strict=True)
        header = next(rows, None)
        if not header or len(header) > 64 or any(len(x) > 256 for x in header):
            raise ResearchFormatError("invalid TSV header")
        if not any(x.strip() for x in header):
            raise ResearchFormatError("TSV has no labeled fields")
        header = [v.strip() or f"field_{i+1}" for i,v in enumerate(header)]
        lines = []
        for i, row in enumerate(rows, 1):
            if i > 1024 or len(row) != len(header) or any(len(x) > 8192 for x in row):
                raise ResearchFormatError("TSV record capacity or width exceeded")
            # All cells are inert literals; no CSV/TSV formula execution occurs.
            lines.append(f"Data row {i}: " + "; ".join(
                f"{label}: {value.strip()}" for label, value in zip(header, row)
            ))
    except csv.Error as exc:
        raise ResearchFormatError("invalid quoted TSV record") from exc
    return project_lines(lines, title=", ".join(header[:4]), max_chars=max_chars)
