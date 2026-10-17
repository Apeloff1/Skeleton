"""Read-time projection from a canonical crawler checkpoint to companion events.

The crawler snapshot remains the source of truth. This module does not open a
database, store a second journal, burn a page, or mark captured text as reviewed.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping

from .dragon_journal import ALLOWED, SCHEMA, _canonical

GENESIS = "0" * 64
SOURCE = "canonical_crawler_checkpoint"
_CAPTURE_KINDS = {
    "dispatch_reserved": "fetch_started",
    "robots": "robots_check",
    "redirect": "dragon_travel",
    "captured": "fetch_received",
    "duplicate": "visual_probe",
    "rejected": "policy_rejected",
    "error": "retry_wait",
    "interrupted_dispatch": "retry_wait",
    "pause": "retry_wait",
    "stopped": "retry_wait",
    "resume": "frontier_discovered",
    "cancel": "policy_rejected",
    "completed": "crawl_complete",
}
_HIDDEN = frozenset({"burn_started", "burn_chunk", "burn_complete", "distill_complete", "acquisition_accepted"})


class CompanionCursorError(ValueError):
    """The caller named a digest the retained checkpoint cannot confirm."""


def validate_companion_cursor(after_sequence: int, limit: int, expected_digest: str | None) -> None:
    if type(after_sequence) is not int or after_sequence < 0:
        raise CompanionCursorError("invalid feed cursor")
    if type(limit) is not int or not 1 <= limit <= 250:
        raise CompanionCursorError("invalid feed page limit")
    if expected_digest is not None and (
        type(expected_digest) is not str
        or len(expected_digest) != 64
        or any(char not in "0123456789abcdef" for char in expected_digest)
    ):
        raise CompanionCursorError("invalid feed digest cursor")


def _url(value: object) -> str | None:
    if isinstance(value, str) and value.startswith(("https://", "http://")) and len(value) <= 4096:
        return value
    return None


def _reason(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = "".join(char for char in value if char.isprintable()).strip()
    if not cleaned:
        return None
    return cleaned[:160]


def project_companion_feed(
    session_id: str,
    events: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    *,
    fallback_url: str | None,
    after_sequence: int = 0,
    limit: int = 100,
    expected_digest: str | None = None,
) -> dict[str, Any]:
    """Map retained operational events onto the companion wire without renumbering.

    A truncated tail links its first retained event to the genesis digest and
    reports history_truncated. Missing earlier events are not invented.
    """
    validate_companion_cursor(after_sequence, limit, expected_digest)
    if not isinstance(session_id, str) or not 1 <= len(session_id) <= 128:
        raise ValueError("crawler checkpoint is not companion-replayable")
    if not isinstance(events, (list, tuple)):
        raise ValueError("crawler checkpoint is not companion-replayable")
    fallback = _url(fallback_url)
    wires: list[dict[str, Any]] = []
    previous = GENESIS
    last_sequence = 0
    for raw in events:
        if not isinstance(raw, Mapping):
            raise ValueError("crawler checkpoint is not companion-replayable")
        sequence = raw.get("sequence")
        if type(sequence) is not int or sequence < 1 or (last_sequence and sequence != last_sequence + 1):
            raise ValueError("crawler checkpoint is not companion-replayable")
        kind_name = raw.get("kind")
        if not isinstance(kind_name, str) or not 1 <= len(kind_name) <= 64:
            raise ValueError("crawler checkpoint is not companion-replayable")
        kind = _CAPTURE_KINDS.get(kind_name, "visual_probe")
        if kind not in ALLOWED or kind in _HIDDEN:
            raise ValueError("crawler checkpoint is not companion-replayable")
        at = raw.get("at")
        if isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(float(at)):
            raise ValueError("crawler checkpoint is not companion-replayable")
        url = _url(raw.get("url")) or fallback
        if url is None:
            raise ValueError("crawler checkpoint is not companion-replayable")
        payload: dict[str, Any] = {
            "source": SOURCE,
            "operational_kind": kind_name,
            "operational_sequence": sequence,
        }
        reason = _reason(raw.get("reason"))
        if reason is not None:
            payload["reason"] = reason
        operational_digest = raw.get("event_digest")
        if (
            isinstance(operational_digest, str)
            and len(operational_digest) == 64
            and all(char in "0123456789abcdef" for char in operational_digest)
        ):
            payload["operational_digest"] = operational_digest
        if len(_canonical(payload).encode("utf-8")) > 32768:
            raise ValueError("crawler checkpoint is not companion-replayable")
        base = {
            "session_id": session_id,
            "sequence": sequence,
            "kind": kind,
            "url": url,
            "at": float(at),
            "payload": payload,
            "previous_digest": previous,
        }
        digest = hashlib.sha256(_canonical(base).encode("utf-8")).hexdigest()
        wires.append(
            {
                "schema": SCHEMA,
                "sequence": sequence,
                "event_id": digest,
                "kind": kind,
                "url": url,
                "at": float(at),
                "payload": payload,
                "previous_digest": previous,
                "digest": digest,
            }
        )
        previous = digest
        last_sequence = sequence
    if after_sequence == 0:
        if expected_digest not in (None, GENESIS):
            raise CompanionCursorError("feed cursor does not match the journal head")
    elif expected_digest is not None:
        cursor = next((event for event in wires if event["sequence"] == after_sequence), None)
        if cursor is None or cursor["digest"] != expected_digest:
            raise CompanionCursorError("feed cursor does not match the journal head")
    page = [event for event in wires if event["sequence"] > after_sequence]
    visible = page[:limit]
    return {
        "events": visible,
        "next_cursor": str(visible[-1]["sequence"]) if visible else None,
        "has_more": len(page) > limit,
        "history_truncated": bool(wires) and wires[0]["sequence"] > 1,
        "source": SOURCE,
    }
