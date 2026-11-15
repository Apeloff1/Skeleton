"""Durable source aliases without double-counting identical content.

An alias is a charged capture observation associated with an existing exact
normalized-content identity. It is neither another independent source nor an
authorization to retrieve, train on, or publish the content. Raw bodies and
untrusted titles are never added to this ledger.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

MAX_ALIASES = 128
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def make_alias(*, source_id: str, canonical_url: str, fetched_url: str,
               content_hash: str, raw_body_hash: str, captured_at: float,
               sequence: int) -> dict:
    value = {
        "source_id": source_id, "canonical_url": canonical_url,
        "fetched_url": fetched_url, "content_hash": content_hash,
        "raw_body_hash": raw_body_hash, "captured_at": captured_at,
        "sequence": sequence, "independent_evidence": False,
        "raw_bytes_retained": False, "training_permission": False,
    }
    return {**value, "alias_digest": _digest(value)}


def validate_aliases(records: object, *, sources: dict, seen: list[str],
                     requests: int, sequence: int, admit) -> None:
    if (not isinstance(records, list) or len(records) > min(MAX_ALIASES, requests)
            or not isinstance(sources, dict)):
        raise ValueError("duplicate receipt capacity exceeded")
    previous = 0
    seen_urls = frozenset(seen)
    receipts = set()
    required = {"source_id", "canonical_url", "fetched_url", "content_hash",
                "raw_body_hash", "captured_at", "sequence", "independent_evidence",
                "raw_bytes_retained", "training_permission", "alias_digest"}
    for row in records:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("invalid duplicate receipt")
        body = dict(row)
        identity = body.pop("alias_digest")
        if not isinstance(identity, str) or not _SHA256.fullmatch(identity) or identity != _digest(body):
            raise ValueError("duplicate receipt identity mismatch")
        n = row["sequence"]
        source = sources.get(row["source_id"]) if isinstance(row["source_id"], str) else None
        if (type(n) is not int or not previous < n <= sequence
                or identity in receipts or not isinstance(source, dict)
                or source["content_hash"] != row["content_hash"]
                or not isinstance(row["content_hash"], str) or not _SHA256.fullmatch(row["content_hash"])
                or not isinstance(row["raw_body_hash"], str) or not _SHA256.fullmatch(row["raw_body_hash"])
                or isinstance(row["captured_at"], bool) or not isinstance(row["captured_at"], (int, float))
                or not math.isfinite(row["captured_at"]) or not 0 <= row["captured_at"] <= 1e12
                or row["independent_evidence"] is not False
                or row["raw_bytes_retained"] is not False or row["training_permission"] is not False):
            raise ValueError("duplicate receipt custody mismatch")
        for key in ("canonical_url", "fetched_url"):
            url = row[key]
            if not isinstance(url, str) or not 1 <= len(url.encode("utf-8")) <= 4096:
                raise ValueError("invalid duplicate source URL")
            admit(url)
            if url not in seen_urls:
                raise ValueError("duplicate source was never settled")
        previous = n
        receipts.add(identity)


def alias_summary(records: list[dict]) -> dict:
    origins = {row["fetched_url"].split("/", 3)[2] for row in records}
    return {
        "count": len(records),
        "represented_sources": len({row["source_id"] for row in records}),
        "observed_origins": len(origins),
        "independent_evidence": False,
        "raw_bytes_retained": False,
    }
