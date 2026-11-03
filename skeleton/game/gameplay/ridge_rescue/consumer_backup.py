"""Versioned portable backup with full retry-aware, canonical CAS action history.

Unlike a campaign-only export, this carries the actual transactional action
ledger, including retry events. The entire original game is independently
replayed before any new save is admitted. No signature or release claim.
"""
from __future__ import annotations

import json
from .campaign import open_campaign, parse_campaign, step_campaign, retry_campaign, verify_campaign
from .custody import canonical, digest

SCHEMA = "ridge.rescue.consumer.backup.v1"
MAX_BACKUP_BYTES = 1_000_000
MAX_BACKUP_ACTIONS = 4096
MAX_BACKUP_ACTION_BYTES = 4096


class BackupError(ValueError):
    """Portable save backup is incomplete, oversized or not replayable."""


def verify_backup(value: dict | str | bytes, original_source: bytes) -> tuple[dict, list[dict]]:
    if isinstance(value, bytes):
        if len(value) > MAX_BACKUP_BYTES:
            raise BackupError("backup exceeds byte budget")
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BackupError("backup is not UTF-8") from exc
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_BACKUP_BYTES:
            raise BackupError("backup exceeds byte budget")
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise BackupError("invalid backup JSON") from exc
    if not isinstance(value, dict) or set(value) != {"payload", "sha256"}:
        raise BackupError("invalid backup envelope")
    if len(canonical(value)) > MAX_BACKUP_BYTES:
        raise BackupError("backup exceeds byte budget")
    payload = value["payload"]
    if not isinstance(payload, dict) or set(payload) != {"schema", "source_sha256", "session", "history"}:
        raise BackupError("invalid backup payload")
    if payload["schema"] != SCHEMA or value["sha256"] != digest(payload):
        raise BackupError("backup checksum or version mismatch")
    original = parse_campaign(original_source)
    if payload["source_sha256"] != digest(original):
        raise BackupError("backup belongs to another game source")
    verified = verify_campaign(payload["session"])
    if verified["session"]["source_sha256"] != payload["source_sha256"]:
        raise BackupError("backup session is not source-bound")
    history = payload["history"]
    if not isinstance(history, list) or len(history) > MAX_BACKUP_ACTIONS:
        raise BackupError("invalid backup history length")
    replay = open_campaign(original_source)
    restored: list[dict] = []
    for entry in history:
        if not isinstance(entry, dict) or set(entry) != {"prior_head", "next_head", "action"}:
            raise BackupError("malformed backup action")
        action = entry["action"]
        if not isinstance(action, dict) or len(canonical(action)) > MAX_BACKUP_ACTION_BYTES:
            raise BackupError("oversized backup action")
        prior = replay["head"]
        if entry["prior_head"] != prior:
            raise BackupError("backup CAS history has a broken parent")
        try:
            if action == {"verb": "retry"}:
                replay = retry_campaign(replay, expected_head=prior)
            else:
                replay = step_campaign(replay, action, expected_head=prior)
        except (ValueError, TypeError, KeyError) as exc:
            raise BackupError("backup action cannot replay") from exc
        if entry["next_head"] != replay["head"]:
            raise BackupError("backup CAS history has a broken successor")
        restored.append({"prior_head": prior, "next_head": replay["head"], "action": action})
    if canonical(replay) != canonical(verified["session"]):
        raise BackupError("backup state differs from canonical action replay")
    return replay, restored


def build_backup(session: dict, history: list[dict], original_source: bytes) -> dict:
    source = parse_campaign(original_source)
    payload = {"schema": SCHEMA, "source_sha256": digest(source),
               "session": session, "history": history}
    result = {"payload": payload, "sha256": digest(payload)}
    verify_backup(result, original_source)
    return result
