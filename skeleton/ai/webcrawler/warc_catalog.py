"""Inert bounded WARC catalog extraction with per-record payload digests.

Never replays embedded HTTP requests, interprets URLs as fetch targets, or
retains archived response bodies. Only finite WARC record metadata is exported
as unreviewed research evidence. This is not WARC provenance verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import re

from .research_projection import (
    ResearchFormatError, ResearchProjection, project_lines,
)

WARC_MEDIA_TYPES = frozenset({"application/warc", "application/x-warc"})
_MAX_BODY = 2_097_152
_MAX_RECORDS = 128
_HEADER = re.compile(rb"^([A-Za-z][A-Za-z0-9-]{0,63}):[ \t]*(.*)$")
_SIZE = re.compile(rb"^[0-9]{1,9}$")
_TYPES = frozenset({"response", "revisit", "resource", "metadata", "request"})


@dataclass(frozen=True)
class WarcHeader:
    kind: str
    target: str
    timestamp: str
    length: int


def _meta(data: bytes) -> WarcHeader:
    if len(data) > 32768 or b"\x00" in data:
        raise ResearchFormatError("invalid WARC header")
    lines = data.split(b"\r\n")
    if not lines or lines[0] not in (b"WARC/1.0", b"WARC/1.1"):
        raise ResearchFormatError("WARC version or CRLF syntax invalid")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        match = _HEADER.fullmatch(line)
        if match is None:
            raise ResearchFormatError("malformed WARC header field")
        key = match.group(1).decode("ascii").lower()
        if key in fields:
            raise ResearchFormatError("duplicate WARC header field")
        try:
            value = match.group(2).decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ResearchFormatError("invalid WARC header UTF-8") from exc
        if len(value) > 4096:
            raise ResearchFormatError("WARC field exceeds length bound")
        fields[key] = value
    try:
        length = fields.get("content-length", "").encode("ascii", errors="strict")
    except UnicodeEncodeError as exc:
        raise ResearchFormatError("non-ASCII WARC Content-Length") from exc
    if not _SIZE.fullmatch(length):
        raise ResearchFormatError("missing or invalid WARC Content-Length")
    kind = fields.get("warc-type", "").lower()
    if kind not in _TYPES:
        raise ResearchFormatError("unsupported WARC record type")
    target = fields.get("warc-target-uri", "")
    # Do not project a possibly credential-bearing URI; avoid leaking
    # query strings, path secrets, private hostnames, or data URIs.
    target_kind = "present" if target else "absent"
    date = fields.get("warc-date", "")
    if len(date) > 64:
        raise ResearchFormatError("invalid WARC date")
    if date:
        try:
            datetime.fromisoformat(date.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ResearchFormatError("invalid WARC datetime") from exc
    return WarcHeader(kind, target_kind, date[:40], int(length))


def extract_warc_catalog(
    body: bytes, *, max_chars: int = 524288,
) -> ResearchProjection:
    if (not isinstance(body, bytes) or not body or len(body) > _MAX_BODY
            or type(max_chars) is not int or not 1 <= max_chars <= _MAX_BODY):
        raise ResearchFormatError("WARC source exceeds bounded byte limits")
    pos = 0
    lines = []
    records = 0
    while pos < len(body):
        if records >= _MAX_RECORDS:
            raise ResearchFormatError("WARC record count exceeded")
        header_end = body.find(b"\r\n\r\n", pos)
        if header_end < 0 or header_end - pos > 32768:
            raise ResearchFormatError("incomplete WARC record header")
        header = _meta(body[pos:header_end])
        pos = header_end + 4
        end = pos + header.length
        if end > len(body):
            raise ResearchFormatError("truncated WARC Content-Length payload")
        payload = body[pos:end]
        pos = end
        # WARC record separator consists of two CRLFs. A single terminal
        # CRLF is not enough because it blurs payload framing boundaries.
        if pos < len(body):
            if body[pos:pos+4] != b"\r\n\r\n":
                raise ResearchFormatError("invalid WARC record separator")
            pos += 4
        records += 1
        sha = hashlib.sha256(payload).hexdigest()
        lines.append(
            f"Archive record {records}: type: {header.kind}; "
            f"target: {header.target}; date: {header.timestamp}; "
            f"bytes: {header.length}; payload_sha256: {sha}"
        )
    return project_lines(lines, title="WARC archive catalog", max_chars=max_chars)
