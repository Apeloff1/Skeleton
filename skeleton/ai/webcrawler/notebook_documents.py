"""Bounded Jupyter notebook source ingestion without cell execution or outputs.

No kernel, local file, notebook extension, widget, HTML output, embedded
attachment or code-generated URL is evaluated. Notebook outputs and metadata
are discarded, and suspicious credential-bearing code cells are withheld.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

NOTEBOOK_MEDIA_TYPES = frozenset({
    "application/x-ipynb+json", "application/vnd.jupyter",
})
_CREDENTIAL = re.compile(
    r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token"
    r"|client[_-]?secret|private[_-]?key|authorization|credentials?)\b"
)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ResearchFormatError("duplicate notebook JSON property")
        value[key] = item
    return value


def _constant(value: str) -> Any:
    raise ResearchFormatError("non-finite notebook JSON constant")


def extract_notebook(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        document = json.loads(
            raw, object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, RecursionError) as exc:
        raise ResearchFormatError("invalid notebook JSON envelope") from exc
    if (not isinstance(document, dict)
            or type(document.get("nbformat")) is not int
            or document["nbformat"] != 4
            or not isinstance(document.get("cells"), list)
            or len(document["cells"]) > 256):
        raise ResearchFormatError("unsupported notebook format or cell capacity")
    lines = []
    title = ""
    for i, cell in enumerate(document["cells"], 1):
        if not isinstance(cell, dict) or cell.get("cell_type") not in ("markdown", "code", "raw"):
            raise ResearchFormatError("invalid notebook cell")
        raw_source = cell.get("source")
        if isinstance(raw_source, list):
            if len(raw_source) > 8192 or any(not isinstance(x, str) for x in raw_source):
                raise ResearchFormatError("unbounded notebook cell fragments")
            source = "".join(raw_source)
        elif isinstance(raw_source, str):
            source = raw_source
        else:
            raise ResearchFormatError("notebook cell has no text source")
        if len(source) > 65536:
            raise ResearchFormatError("oversized notebook cell")
        kind = cell["cell_type"]
        if kind == "code" and _CREDENTIAL.search(source):
            # Code with credential indicators is withheld in full rather than
            # attempting to mask a possibly multiline secret or API token.
            source = "[source code withheld: possible credential material]"
        if not source.strip():
            continue
        if not title and kind == "markdown":
            for line in source.splitlines():
                if line.lstrip().startswith("# "):
                    title = line.lstrip()[2:].strip()[:512]
                    break
        lines.append(f"Notebook cell {i} ({kind}): " + source.strip()[:8192])
    return project_lines(
        lines, title=title or "Jupyter notebook source", max_chars=max_chars,
    )
