"""One-shot bounded extraction supervised by the canonical CrawlRun.

No parser owns the frontier, network transport, consent, database, or request
budget. The process boundary limits ordinary parser faults, not arbitrary
native-code compromise. On platforms without the required hard limits,
complex documents are held, never silently processed in the main worker.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time

from .core import CrawlDocument, FetchResponse, _source_score, canonicalize_url
from .structured_discovery import StructuredDiscovery, UnsupportedDiscoveryRoot
from .structural_extraction import validate_structural_receipt

MAX_BODY = 2_097_152
MAX_HEADER = 16_384
MAX_OUTPUT = 12 * 1024 * 1024
MAX_LINKS = 128
MAX_TEXT = MAX_BODY + 32768
MAX_CHILDREN = 3
MAX_SECONDS = 8.0
_CHILDREN = threading.BoundedSemaphore(MAX_CHILDREN)
_SIMPLE = frozenset({"text/plain", "text/html", "application/xhtml+xml"})
_FAULTS = frozenset({"capacity", "deadline", "unsupported_platform", "launch",
                     "worker_exit", "invalid_output", "parser_rejected"})


class ParserFault(ValueError):
    def __init__(self, code: str):
        if code not in _FAULTS:
            raise ValueError("invalid parser fault")
        self.code = code
        super().__init__("bounded parser " + code)


@dataclass(frozen=True)
class ParserOutcome:
    document: CrawlDocument | None
    execution: str


def requires_isolation(media_type: str, body_size: int) -> bool:
    # PDF already has its own dedicated resource-limited child.
    return media_type != "application/pdf" and (
        media_type not in _SIMPLE or body_size > 65536
    )


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), sort_keys=True).encode("utf-8")


def _text(value: object, bound: int, *, empty=False) -> str:
    if (not isinstance(value, str) or len(value.encode("utf-8")) > bound
            or not empty and not value.strip()
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise ParserFault("invalid_output")
    return value


def _exchange(metadata: dict, body: bytes, deadline: float) -> dict:
    if type(body) is not bytes or len(body) > MAX_BODY:
        raise ParserFault("parser_rejected")
    if (isinstance(deadline, bool) or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)):
        raise ParserFault("deadline")
    if os.name != "posix":
        raise ParserFault("unsupported_platform")
    remaining = min(MAX_SECONDS, deadline - time.monotonic())
    if remaining < .1:
        raise ParserFault("deadline")
    header = _json(metadata)
    if len(header) > MAX_HEADER:
        raise ParserFault("parser_rejected")
    # Brief bounded admission wait absorbs ordinary simultaneous slices.
    # Never consume the entire remaining slice waiting for capacity.
    if not _CHILDREN.acquire(timeout=min(.5, remaining / 4)):
        raise ParserFault("capacity")
    try:
        program = Path(__file__).resolve().with_name("parser_worker.py")
        # Anonymous output spool holds only bounded extracted data, never raw
        # downloaded bytes. A kernel file-size limit bounds hostile stdout.
        # Parent never reads more than MAX_OUTPUT + 1 bytes.
        with tempfile.TemporaryFile(mode="w+b") as spool:
            remaining = min(MAX_SECONDS, deadline - time.monotonic())
            if remaining < .1:
                raise ParserFault("deadline")
            try:
                result = subprocess.run(
                    [sys.executable, "-I", "-B", str(program)],
                    input=struct.pack(">I", len(header)) + header + body,
                    stdout=spool, stderr=subprocess.DEVNULL, check=False,
                    timeout=remaining,
                    env={"LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
                )
            except subprocess.TimeoutExpired as exc:
                # subprocess.run kills and waits for the child before raising.
                raise ParserFault("deadline") from exc
            except OSError as exc:
                raise ParserFault("launch") from exc
            if result.returncode:
                raise ParserFault("worker_exit")
            if time.monotonic() >= deadline:
                raise ParserFault("deadline")
            spool.seek(0)
            raw = spool.read(MAX_OUTPUT + 1)
        if len(raw) > MAX_OUTPUT:
            raise ParserFault("invalid_output")
        try:
            value = json.loads(raw.decode("utf-8", errors="strict"))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ParserFault("invalid_output") from exc
        if not isinstance(value, dict) or set(value) != {"status", "payload"}:
            raise ParserFault("invalid_output")
        return value
    finally:
        _CHILDREN.release()


def _links(value: object, base: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_LINKS:
        raise ParserFault("invalid_output")
    result = []
    for link in value:
        link = _text(link, 4096)
        try:
            url = canonicalize_url(link, base=base)
        except (ValueError, UnicodeError):
            continue
        if len(url.encode("utf-8")) <= 4096 and url not in result:
            result.append(url)
    return tuple(result)


def extract_isolated(response: FetchResponse, canonical_url: str, *,
                     max_chars: int, deadline: float) -> ParserOutcome:
    if type(max_chars) is not int or not 1 <= max_chars <= MAX_BODY:
        raise ParserFault("parser_rejected")
    media = response.headers.get("content-type", "text/plain")
    output = _exchange({
        "mode": "document", "url": response.url, "canonical_url": canonical_url,
        "media": media, "status": response.status, "fetched_at": response.fetched_at,
        "max_chars": max_chars, "body_size": len(response.body),
    }, response.body, deadline)
    status, payload = output["status"], output["payload"]
    if status == "empty" and payload is None:
        return ParserOutcome(None, "isolated_posix")
    if status == "rejected" and payload is None:
        raise ParserFault("parser_rejected")
    if status != "ok" or not isinstance(payload, dict) or set(payload) != {
        "title", "text", "links", "truncated", "structural_projection",
    }:
        raise ParserFault("invalid_output")
    text = _text(payload["text"], MAX_TEXT * 4)
    if len(text) > max_chars + 32768 or type(payload["truncated"]) is not bool:
        raise ParserFault("invalid_output")
    title = _text(payload["title"], 4000, empty=True)
    links = _links(payload["links"], response.url)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    decoded = hashlib.sha256(response.body).hexdigest()
    effective = media.split(";", 1)[0].strip().lower()
    structural = payload["structural_projection"]
    if structural is not None and (effective not in {"text/html", "application/xhtml+xml"}
                                    or not validate_structural_receipt(structural)):
        raise ParserFault("invalid_output")
    # The parent creates all authority/provenance fields from the already
    # metered response. A child's claims about hashes, URLs, rights and
    # transport cannot become evidence.
    document = CrawlDocument(
        canonical_url, response.url, title, text, effective, digest,
        response.fetched_at, _source_score(canonical_url, text, response.status),
        {"schema": "skeleton.ai.crawl.provenance.v1",
         "canonical_url": canonical_url, "fetched_url": response.url,
         "fetched_at": response.fetched_at, "status": response.status,
         "content_hash": digest, "raw_body_hash": response.wire_hash or decoded,
         "decoded_body_hash": decoded,
         "wire_bytes": response.wire_bytes if response.wire_bytes is not None else len(response.body),
         "content_encoding": response.content_encoding,
         "parser_text_truncated": payload["truncated"],
         "parser_execution": "isolated_posix",
         **({"structural_projection": structural} if structural is not None else {})},
        links,
    )
    return ParserOutcome(document, "isolated_posix")


def discover_isolated(body: bytes, *, media_type: str, document_url: str,
                      allowed_hosts: frozenset[str], max_bytes: int,
                      deadline: float, plaintext: bool = False) -> StructuredDiscovery:
    result = _exchange({
        "mode": "sitemap" if plaintext else "discovery", "url": document_url,
        "media": media_type, "hosts": sorted(allowed_hosts),
        "max_bytes": max_bytes, "body_size": len(body),
    }, body, deadline)
    status, payload = result["status"], result["payload"]
    if status == "unsupported" and payload is None:
        raise UnsupportedDiscoveryRoot("isolated non-discovery document")
    if status == "rejected" and payload is None:
        raise ParserFault("parser_rejected")
    if status != "ok" or not isinstance(payload, dict) or set(payload) != {
        "kind", "links", "examined", "discarded", "capped",
    }:
        raise ParserFault("invalid_output")
    kind = _text(payload["kind"], 96)
    examined, discarded = payload["examined"], payload["discarded"]
    if (type(examined) is not int or not 0 <= examined <= 16384
            or type(discarded) is not int or not 0 <= discarded <= 16384
            or type(payload["capped"]) is not bool):
        raise ParserFault("invalid_output")
    links = _links(payload["links"], document_url)
    return StructuredDiscovery(kind, links, examined, discarded, payload["capped"])
