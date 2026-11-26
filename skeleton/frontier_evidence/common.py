"""Seal helper for frontier evidence.

The hash authority is ``skeleton.jeeves.game_frontier_frame_coherence.digest``.
This module does not define a second content-address function.
"""

from __future__ import annotations

from typing import Mapping

from skeleton.jeeves.game_frontier_frame_coherence import FrameCoherenceError, digest


class EvidenceRejected(ValueError):
    """Fail-closed rejection for typed-frame evidence."""


def content_digest(value: object) -> str:
    try:
        return digest(value)
    except FrameCoherenceError as exc:
        raise EvidenceRejected("evidence content is not canonical finite JSON") from exc


def seal(body: Mapping[str, object]) -> dict:
    if "receipt_digest" in body:
        raise EvidenceRejected("seal input must not carry a digest")
    payload = dict(body)
    payload["receipt_digest"] = content_digest(payload)
    return payload


def seal_ok(doc: Mapping[str, object] | object) -> bool:
    if not isinstance(doc, Mapping) or "receipt_digest" not in doc:
        return False
    body = {key: value for key, value in doc.items() if key != "receipt_digest"}
    try:
        return doc.get("receipt_digest") == content_digest(body)
    except EvidenceRejected:
        return False
