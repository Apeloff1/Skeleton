"""Canonical, bounded quest-session JSON save and tamper-checked restoration."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    QuestSession, StudioQuestError, replay_quest, verify_quest_session,
)

SCHEMA = "skeleton.game_builder.studio_quest_save.v1"


def encode_quest_save(session: QuestSession, documents: Mapping[str, Any], *,
                      authorized: bool) -> bytes:
    if not authorized:
        raise PermissionError("save requires operator authorization")
    verify_quest_session(session, documents)
    body = {"schema": SCHEMA, "project_id": session.project_id,
            "source_digest": session.source_digest,
            "choices": [list(pair) for pair in session.choices],
            "session_digest": session.digest, "release_certified": False}
    data = json.dumps(body, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("ascii")
    return data + b"\n"


def restore_quest_save(blob: bytes, documents: Mapping[str, Any], *,
                       authorized: bool) -> QuestSession:
    if not authorized:
        raise PermissionError("restore requires operator authorization")
    if not isinstance(blob, bytes) or len(blob) > 65536 or not blob.endswith(b"\n"):
        raise StudioQuestError("invalid quest save envelope")
    try:
        def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
            out: dict[str, object] = {}
            for key, value in pairs:
                if key in out:
                    raise StudioQuestError("duplicate quest save key")
                out[key] = value
            return out
        raw = json.loads(blob.decode("ascii", errors="strict"),
                         object_pairs_hook=reject_duplicates,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             StudioQuestError("nonfinite quest save")))
    except (UnicodeError, ValueError) as exc:
        raise StudioQuestError("invalid quest save JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema", "project_id", "source_digest", "choices", "session_digest",
        "release_certified",
    } or raw["schema"] != SCHEMA or raw["release_certified"] is not False:
        raise StudioQuestError("invalid quest save schema or release claim")
    choices = raw["choices"]
    session = replay_quest(documents, choices, authorized=True)
    if (session.project_id != raw["project_id"] or
            session.source_digest != raw["source_digest"] or
            session.digest != raw["session_digest"] or
            encode_quest_save(session, documents, authorized=True) != blob):
        raise StudioQuestError("quest save replay identity mismatch")
    return session
