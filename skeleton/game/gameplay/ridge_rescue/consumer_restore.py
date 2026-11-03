"""Fail-closed portable game restoration from canonical, replay-verified exports.

A restored slot is a NEW save, never an overwrite. The original game source,
not the exported author's claims, determines every accepted transition.
Exports with retries are deliberately refused until retry chronology is
included in a versioned portable format; silently synthesizing it is unsafe.
"""
from __future__ import annotations

from .campaign import open_campaign, parse_campaign, step_campaign, verify_export
from .custody import canonical, digest

MAX_RESTORE_ACTIONS = 4096
MAX_RESTORE_ACTION_BYTES = 4096


class RestoreError(ValueError):
    """A portable campaign cannot be safely restored."""


def replay_export(payload: bytes | str | dict, original_source: bytes) -> tuple[dict, list[dict]]:
    """Return canonical session and full, independently reconstructed CAS history."""
    verified = verify_export(payload)
    original = parse_campaign(original_source)
    session = verified["session"]
    if session["source_sha256"] != digest(original):
        raise RestoreError("export is not bound to this original game")
    if any(session["retries"]):
        raise RestoreError("export retry chronology unavailable; refusing incomplete audit")
    journals = list(session["completed"])
    if session["active"] is not None:
        journals.append(session["active"])
    replay = open_campaign(original_source)
    history: list[dict] = []
    for journal in journals:
        for entry in journal["entries"]:
            action = entry["action"]
            if len(history) >= MAX_RESTORE_ACTIONS or len(canonical(action)) > MAX_RESTORE_ACTION_BYTES:
                raise RestoreError("portable action history exceeds restoration bounds")
            prior = replay["head"]
            try:
                replay = step_campaign(replay, action, expected_head=prior)
            except (ValueError, TypeError, KeyError) as exc:
                raise RestoreError("portable action history does not replay") from exc
            history.append({"prior_head": prior, "next_head": replay["head"], "action": action})
    if canonical(replay) != canonical(session):
        raise RestoreError("export session differs from reconstructed original game")
    return replay, history
