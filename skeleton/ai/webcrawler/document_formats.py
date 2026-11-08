"""Bounded Markdown, CSV and JSON source extraction for the canonical crawler.

All inputs are untrusted external bytes decoded by the existing CrawlRun
transport. This module cannot open a socket, read the filesystem, execute
markup, publish knowledge or authorize discovered URLs. It produces bounded
text for the existing source hash / evidence pipeline, and only Markdown
may propose untrusted navigational links for canonical frontier admission.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import json
import math
import re
from typing import Any

from .research_artifacts import RESEARCH_ARTIFACT_TYPES, extract_research_artifact
from .research_projection import ResearchFormatError
from .har_documents import HAR_MEDIA_TYPES, extract_har
from .patch_documents import PATCH_MEDIA_TYPES, extract_unified_patch
from .csl_documents import CSL_MEDIA_TYPES, extract_csl
from .technical_documents import TECHNICAL_MEDIA_TYPES, extract_technical_document
from .asset_formats import ASSET_TEXT_MEDIA_TYPES, extract_asset_text
from .supply_chain_artifacts import SUPPLY_CHAIN_TYPES, extract_supply_chain_artifact
from .scene_asset_formats import SCENE_ASSET_TYPES, extract_scene_asset
from .package_lock_artifacts import PACKAGE_LOCK_TYPES, extract_package_lock
from .iiif_manifest_documents import IIIF_DOCUMENT_TYPES, extract_iiif_manifest
from .interface_artifacts import INTERFACE_TYPES, extract_interface_artifact
from .graph_artifacts import GRAPH_ARTIFACT_TYPES, extract_graph_artifact
from .tiled_artifacts import TILED_ARTIFACT_TYPES, extract_tiled_artifact
from .robot_scene_artifacts import ROBOT_SCENE_TYPES, extract_robot_scene


MARKDOWN_TYPES = frozenset({"text/markdown", "text/x-markdown"})
CSV_TYPES = frozenset({"text/csv", "application/csv"})
JSON_TYPES = frozenset({"application/json", "application/ld+json"})
NDJSON_TYPES = frozenset({
    "application/x-ndjson", "application/ndjson",
    "application/jsonl", "text/x-jsonl",
})
SOURCE_CODE_TYPES = frozenset({
    "text/x-python", "text/x-c", "text/x-csrc", "text/x-c++src",
    "text/x-rust", "text/x-go", "text/x-java-source",
    "text/javascript", "application/javascript",
    "application/x-javascript", "text/x-typescript",
    "application/typescript", "text/css",
    "text/x-rst", "text/x-asciidoc",
    "text/yaml", "text/x-yaml", "application/yaml",
    "application/x-yaml", "application/toml", "text/x-toml",
    "text/x-shellscript", "application/x-sh",
})
ADDITIONAL_TYPES = (
    MARKDOWN_TYPES | CSV_TYPES | JSON_TYPES | NDJSON_TYPES | SOURCE_CODE_TYPES
    | RESEARCH_ARTIFACT_TYPES | HAR_MEDIA_TYPES | PATCH_MEDIA_TYPES | CSL_MEDIA_TYPES
    | TECHNICAL_MEDIA_TYPES | ASSET_TEXT_MEDIA_TYPES | SUPPLY_CHAIN_TYPES
    | SCENE_ASSET_TYPES | PACKAGE_LOCK_TYPES | IIIF_DOCUMENT_TYPES | INTERFACE_TYPES
    | GRAPH_ARTIFACT_TYPES | TILED_ARTIFACT_TYPES | ROBOT_SCENE_TYPES
)

_MD_LINK = re.compile(
    r"(?<!!)\[[^\]\n]{1,256}\]\(\s*<?([^\s<>)]{1,4096})>?\s*(?:[\"'][^\"']{0,256}[\"'])?\s*\)"
)
_MD_REFERENCE = re.compile(r"^\s{0,3}\[([^\]\n]{1,128})\]:\s*<?([^\s<>]{1,4096})>?")
_MD_AUTOLINK = re.compile(r"<(https?://[^\s<>]{1,4096})>", re.I)
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.{1,512}?)\s*#*\s*$")
_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "api_key", "apikey", "access_token",
    "refresh_token", "authorization", "private_key", "client_secret",
    "session_token", "credential", "credentials",
})
_JSON_NODE_MAX = 8192


class DocumentFormatError(ValueError):
    """Invalid, oversized or ambiguous untrusted source document."""


@dataclass(frozen=True)
class ExtractedFormat:
    text: str
    title: str
    links: tuple[str, ...]
    truncated: bool = False
    body_executed: bool = False
    reference_trusted: bool = False


def _bounds(raw: str, max_chars: int, max_links: int) -> None:
    if (not isinstance(raw, str) or len(raw) > 2_500_000
            or type(max_chars) is not int or not 1 <= max_chars <= 2_097_152
            or type(max_links) is not int or not 0 <= max_links <= 512):
        raise DocumentFormatError("source format input exceeds bounded limits")
    if "\x00" in raw:
        raise DocumentFormatError("binary/NUL content cannot be parsed as text")


def extract_markdown(
    raw: str, *, max_chars: int = 524_288, max_links: int = 128,
) -> ExtractedFormat:
    """Keep source text usable for code/document retrieval while finding links.

    Fenced code blocks and inline code spans may be retained as untrusted text
    but are not a source of crawler links. Embedded images never initiate
    network requests; their Markdown syntax remains plain source text.
    """
    _bounds(raw, max_chars, max_links)
    candidates = []
    refs = {}
    references_used = []
    title = ""
    in_fence = None
    safe_lines = []
    for line in raw.splitlines():
        stripped = line.lstrip(" ")
        fence = re.match(r"^(`{3,}|~{3,})(?:[^\n]*)$", stripped)
        if fence:
            run = fence.group(1)
            if in_fence is None:
                in_fence = (run[0], len(run))
            elif run[0] == in_fence[0] and len(run) >= in_fence[1]:
                in_fence = None
            safe_lines.append(line)
            continue
        if in_fence is not None:
            safe_lines.append(line)
            continue
        head = _MD_HEADING.match(line)
        if head and not title:
            title = head.group(1).strip()
        match = _MD_REFERENCE.match(line)
        if match:
            refs.setdefault(match.group(1).strip().casefold(), match.group(2).strip())
        # Remove only inline backtick-code spans from link inspection. Never
        # interpret Markdown text as instructions or executable directives.
        scan = re.sub(r"`+[^`\n]*`+", "", line)
        candidates.extend(m.group(1) for m in _MD_LINK.finditer(scan))
        candidates.extend(m.group(1) for m in _MD_AUTOLINK.finditer(scan))
        for m in re.finditer(r"(?<!!)\[[^\]\n]{1,256}\]\[([^\]\n]{1,128})\]", scan):
            references_used.append(m.group(1).strip().casefold())
        safe_lines.append(line)
    candidates.extend(refs[key] for key in references_used if key in refs)
    links = tuple(dict.fromkeys(candidates))[:max_links]
    text = "\n".join(safe_lines).strip()
    return ExtractedFormat(
        text=text[:max_chars], title=title[:512],
        links=links, truncated=len(text) > max_chars or len(set(candidates)) > max_links,
    )


def extract_csv(
    raw: str, *, max_chars: int = 524_288, max_links: int = 128,
    max_rows: int = 512, max_columns: int = 48,
) -> ExtractedFormat:
    """Project a finite CSV into labeled, human-retrievable untrusted text.

    No URLs are discovered from table cells. Formula-like cells remain inert
    literal evidence rather than being evaluated or written to a spreadsheet.
    """
    _bounds(raw, max_chars, max_links)
    if (type(max_rows) is not int or not 1 <= max_rows <= 2048
            or type(max_columns) is not int or not 1 <= max_columns <= 128):
        raise DocumentFormatError("invalid table scan limits")
    try:
        reader = csv.reader(io.StringIO(raw, newline=""), strict=True)
        headers = next(reader, None)
        if not headers or len(headers) > max_columns:
            raise DocumentFormatError("CSV lacks a bounded header row")
        if any(len(h) > 256 for h in headers):
            raise DocumentFormatError("CSV header exceeds field length")
        if not any(h.strip() for h in headers):
            raise DocumentFormatError("CSV header has no meaningful fields")
        labels = [h.strip() or f"column_{i+1}" for i, h in enumerate(headers)]
        lines = []
        count = 0
        for row in reader:
            count += 1
            if count > max_rows or len(row) > max_columns:
                raise DocumentFormatError("CSV row count or width exceeded")
            if len(row) != len(labels) or any(len(cell) > 8192 for cell in row):
                raise DocumentFormatError("CSV table has inconsistent or unbounded cells")
            joined = "; ".join(
                f"{name}: {value.strip()}" for name, value in zip(labels, row)
            )
            lines.append(f"Row {count}: {joined}")
            if sum(len(x) for x in lines) > max_chars * 2:
                raise DocumentFormatError("CSV projection exceeds parse budget")
    except (csv.Error, UnicodeError) as exc:
        raise DocumentFormatError("invalid quoted CSV record") from exc
    text = "\n".join(lines).strip()
    if not text:
        raise DocumentFormatError("CSV has no data rows")
    return ExtractedFormat(
        text=text[:max_chars], title=", ".join(labels[:4])[:512],
        links=(), truncated=len(text) > max_chars,
    )


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DocumentFormatError("duplicate object keys are not accepted")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise DocumentFormatError("non-finite JSON constant")


def extract_json(
    raw: str, *, max_chars: int = 524_288, max_links: int = 128,
    max_depth: int = 24,
) -> ExtractedFormat:
    """Render finite JSON values as lexical path/value evidence.

    No JSON field, including URL, next, href, image or @id, can enqueue a
    frontier entry. Key names associated with credentials are conservatively
    redacted, and values are never interpreted as configuration.
    """
    _bounds(raw, max_chars, max_links)
    if type(max_depth) is not int or not 1 <= max_depth <= 32:
        raise DocumentFormatError("invalid JSON nesting limit")
    try:
        source = json.loads(
            raw, object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (ValueError, json.JSONDecodeError, RecursionError) as exc:
        raise DocumentFormatError("unparseable structured JSON record") from exc
    if not isinstance(source, (dict, list)):
        raise DocumentFormatError("JSON evidence must be an object or array")
    title = ""
    if isinstance(source, dict):
        for key in ("title", "name", "headline"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                title = value.strip()[:512]
                break
    lines = []
    stack = [("$", source, 0)]
    nodes = 0
    chars = 0
    value_clipped = False
    while stack:
        path, value, depth = stack.pop()
        nodes += 1
        if nodes > _JSON_NODE_MAX or depth > max_depth:
            raise DocumentFormatError("JSON structure exceeds bounded complexity")
        if isinstance(value, dict):
            if len(value) > 512:
                raise DocumentFormatError("JSON object has too many keys")
            for key, item in reversed(tuple(value.items())):
                if not isinstance(key, str) or len(key) > 256:
                    raise DocumentFormatError("unbounded JSON key")
                child = path + "." + key
                if key.casefold().replace("-", "_") in _SENSITIVE_KEYS:
                    stack.append((child, "[redacted sensitive field]", depth + 1))
                else:
                    stack.append((child, item, depth + 1))
        elif isinstance(value, list):
            if len(value) > 2048:
                raise DocumentFormatError("JSON list too large")
            for i in reversed(range(len(value))):
                stack.append((f"{path}[{i}]", value[i], depth + 1))
        else:
            if not isinstance(value, (type(None), bool, str, int, float)):
                raise DocumentFormatError("unsupported JSON scalar")
            if isinstance(value, float) and not math.isfinite(value):
                raise DocumentFormatError("non-finite JSON number")
            literal = str(value) if not isinstance(value, str) else value
            if len(literal) > 8192:
                literal = literal[:8192]
                value_clipped = True
            line = f"{path}: {literal}"
            chars += len(line)
            if chars > max_chars * 2:
                raise DocumentFormatError("JSON evidence exceeds parse budget")
            lines.append(line)
    text = "\n".join(lines).strip()
    if not text:
        raise DocumentFormatError("JSON record contains no scalar evidence")
    return ExtractedFormat(
        text=text[:max_chars], title=title,
        links=(), truncated=value_clipped or len(text) > max_chars,
    )


def extract_source_code(
    raw: str, *, max_chars: int = 524_288, max_links: int = 128,
) -> ExtractedFormat:
    """Capture syntax-bearing source as inert, explicitly untrusted evidence.

    Source code is never executed, imported, interpreted as a crawler policy,
    or mined for requestable links. Binary markers, terminal escapes and
    non-text control bytes are rejected before persistence.
    """
    _bounds(raw, max_chars, max_links)
    if any(ord(ch) < 32 and ch not in "\n\t\r" for ch in raw):
        raise DocumentFormatError("unsafe control bytes in source document")
    if raw.count("\ufffd") > max(4, len(raw) // 100):
        raise DocumentFormatError("source document has excessive decoder replacements")
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise DocumentFormatError("source document contains no code or prose")
    return ExtractedFormat(
        text=text[:max_chars], title="", links=(),
        truncated=len(text) > max_chars,
    )


def extract_ndjson(
    raw: str, *, max_chars: int = 524_288, max_links: int = 128,
    max_records: int = 512,
) -> ExtractedFormat:
    """Bounded newline-separated JSON dataset evidence, without URL fanout."""
    _bounds(raw, max_chars, max_links)
    if type(max_records) is not int or not 1 <= max_records <= 2048:
        raise DocumentFormatError("invalid bounded NDJSON record count")
    lines = []
    records = 0
    total = 0
    for row in raw.splitlines():
        if not row.strip():
            continue
        records += 1
        if records > max_records or len(row) > 65536:
            raise DocumentFormatError("NDJSON record limit exceeded")
        parsed = extract_json(
            row, max_chars=min(max_chars, 65536), max_links=0,
        )
        if parsed.truncated:
            raise DocumentFormatError("NDJSON record cannot be silently truncated")
        line = f"Record {records}: {parsed.text}"
        total += len(line)
        if total > max_chars * 2:
            raise DocumentFormatError("NDJSON evidence exceeds parse budget")
        lines.append(line)
    if not records:
        raise DocumentFormatError("NDJSON body has no records")
    text = "\n".join(lines)
    return ExtractedFormat(
        text=text[:max_chars], title="JSON Lines dataset", links=(),
        truncated=len(text) > max_chars,
    )


def extract_additional_format(
    raw: str, media_type: str, *, max_chars: int,
    max_links: int,
) -> ExtractedFormat:
    if media_type in ROBOT_SCENE_TYPES:
        try:
            row=extract_robot_scene(raw,media_type,max_chars=max_chars,max_links=max_links)
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text,title=row.title,links=(),truncated=row.truncated,
            body_executed=False,reference_trusted=False,
        )
    if media_type in TILED_ARTIFACT_TYPES:
        try:
            row=extract_tiled_artifact(raw,media_type,max_chars=max_chars,max_links=max_links)
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text,title=row.title,links=(),truncated=row.truncated,
            body_executed=False,reference_trusted=False,
        )
    if media_type in GRAPH_ARTIFACT_TYPES:
        try:
            row=extract_graph_artifact(raw,media_type,max_chars=max_chars,max_links=max_links)
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text,title=row.title,links=(),truncated=row.truncated,
            body_executed=False,reference_trusted=False,
        )
    if media_type in INTERFACE_TYPES:
        try:
            row = extract_interface_artifact(
                raw,media_type,max_chars=max_chars,max_links=max_links,
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text,title=row.title,links=(),truncated=row.truncated,
            body_executed=False,reference_trusted=False,
        )
    if media_type in IIIF_DOCUMENT_TYPES:
        try:
            row = extract_iiif_manifest(raw, max_chars=max_chars, max_links=max_links)
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text,title=row.title,links=(),truncated=row.truncated,
            body_executed=False,reference_trusted=False,
        )
    if media_type in PACKAGE_LOCK_TYPES:
        try:
            row = extract_package_lock(raw,media_type,max_chars=max_chars,max_links=max_links)
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text,title=row.title,links=(),truncated=row.truncated,
            body_executed=False,reference_trusted=False,
        )
    if media_type in SCENE_ASSET_TYPES:
        try:
            row = extract_scene_asset(
                raw,media_type,max_chars=max_chars,max_links=max_links,
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text,title=row.title,links=(),truncated=row.truncated,
            body_executed=False,reference_trusted=False,
        )
    if media_type in SUPPLY_CHAIN_TYPES:
        try:
            row = extract_supply_chain_artifact(
                raw,media_type,max_chars=max_chars,max_links=max_links,
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text,title=row.title,links=(),truncated=row.truncated,
            body_executed=False,reference_trusted=False,
        )
    if media_type in ASSET_TEXT_MEDIA_TYPES:
        try:
            row = extract_asset_text(
                raw, media_type, max_chars=max_chars, max_links=max_links,
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text, title=row.title, links=(),
            truncated=row.truncated, body_executed=False,
            reference_trusted=False,
        )
    if media_type in TECHNICAL_MEDIA_TYPES:
        try:
            row = extract_technical_document(
                raw, media_type, max_chars=max_chars, max_links=max_links,
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text, title=row.title, links=(),
            truncated=row.truncated, body_executed=False,
            reference_trusted=False,
        )
    if media_type in (HAR_MEDIA_TYPES | PATCH_MEDIA_TYPES | CSL_MEDIA_TYPES):
        try:
            parser = (extract_har if media_type in HAR_MEDIA_TYPES
                      else extract_unified_patch if media_type in PATCH_MEDIA_TYPES
                      else extract_csl)
            row = parser(raw, max_chars=max_chars, max_links=max_links)
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text, title=row.title, links=(),
            truncated=row.truncated, body_executed=False,
            reference_trusted=False,
        )
    if media_type in RESEARCH_ARTIFACT_TYPES:
        try:
            row = extract_research_artifact(
                raw, media_type, max_chars=max_chars, max_links=max_links,
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return ExtractedFormat(
            text=row.text, title=row.title, links=row.links,
            truncated=row.truncated, body_executed=False,
            reference_trusted=False,
        )
    if media_type in MARKDOWN_TYPES:
        return extract_markdown(raw, max_chars=max_chars, max_links=max_links)
    if media_type in CSV_TYPES:
        return extract_csv(raw, max_chars=max_chars, max_links=max_links)
    if media_type in JSON_TYPES:
        return extract_json(raw, max_chars=max_chars, max_links=max_links)
    if media_type in NDJSON_TYPES:
        return extract_ndjson(raw, max_chars=max_chars, max_links=max_links)
    if media_type in SOURCE_CODE_TYPES:
        return extract_source_code(raw, max_chars=max_chars, max_links=max_links)
    raise DocumentFormatError("unsupported additional source type")
