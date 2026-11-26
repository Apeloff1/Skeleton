"""Strict, source-bound restoration of original quest decisions from saved receipts.

Receipts are untrusted data, not authorization. Rebuild from authoritative
source and compare every field, including negative certification flags.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import (
    QuestSession, StudioQuestError, replay_quest,
)

MAX_QUEST_RECEIPT_BYTES = 16 * 1024
QUEST_RECEIPT_SCHEMA = "skeleton.game_builder.studio_quest_session.v1"


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise StudioQuestError("duplicate quest save field")
        value[key] = item
    return value


def restore_quest_receipt(
    documents: Mapping[str, Any], raw: bytes | str, *,
    authorized: bool, expected_source_digest: str | None = None,
) -> QuestSession:
    """Replay and verify the exact saved canonical receipt, never trust it."""
    if authorized is not True:
        raise PermissionError("quest save restoration requires operator authorization")
    if type(raw) not in (bytes, str):
        raise StudioQuestError("quest save must be canonical JSON bytes or text")
    try:
        encoded = raw.encode("utf-8", "strict") if type(raw) is str else raw
    except UnicodeError as exc:
        raise StudioQuestError("invalid quest save encoding") from exc
    if not 1 <= len(encoded) <= MAX_QUEST_RECEIPT_BYTES:
        raise StudioQuestError("quest save exceeds byte budget or is empty")
    try:
        receipt = json.loads(
            encoded, object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite quest save")))
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid quest save JSON") from exc
    if type(receipt) is not dict:
        raise StudioQuestError("quest save must be an object")
    required = {
        "schema", "project_id", "source_digest", "choices", "completed",
        "session_digest", "external_evidence_verified",
        "native_genre_runtime_verified", "release_certified",
    }
    if (set(receipt) != required or receipt.get("schema") != QUEST_RECEIPT_SCHEMA
            or type(receipt.get("choices")) is not list
            or len(receipt["choices"]) > 64):
        raise StudioQuestError("unsupported or malformed quest save contract")
    proof = audit_canon_source(documents, authorized=True)
    if (expected_source_digest is not None
            and (type(expected_source_digest) is not str
                 or expected_source_digest != proof["source_digest"])):
        raise StudioQuestError("quest save expected source lease is stale")
    if (receipt.get("project_id") != proof["project_id"]
            or receipt.get("external_evidence_verified") is not False
            or receipt.get("native_genre_runtime_verified") is not False
            or receipt.get("release_certified") is not False):
        raise StudioQuestError("quest save source or certification is forged")
    session = replay_quest(documents, receipt["choices"], authorized=True)
    if receipt != session.receipt():
        raise StudioQuestError("quest save differs from authoritative replay")
    return session
