"""Source-verified alternative branch from an existing NPC dialogue checkpoint.

A fork is a new canonical quest receipt, not an in-place mutation.  The
operator must lease the original session and the replacement must be an
actually available authored alternative at the replayed checkpoint.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_choice_commit import commit_dialogue_choice
from .studio_ecosystem_dialogue_choice_preview import preview_dialogue_choices
from .studio_ecosystem_dialogue_compare import compare_dialogue_histories
from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError, quest_progress, replay_quest

FORK_SCHEMA = "skeleton.game_builder.studio_dialogue_history_fork.v1"
MAX_FORK_ACTIONS = 64


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical dialogue fork") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _lease(value: object) -> bool:
    return (type(value) is str and len(value) == 64
            and all(ch in "0123456789abcdef" for ch in value))


def fork_dialogue_history(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    checkpoint_index: int, alternative: str, expected_session_digest: str,
    authorized: bool, expected_source_digest: str | None = None,
    preserve_suffix: bool = False,
) -> dict[str, object]:
    """Replay a different authored choice from one exact saved checkpoint.

    By default the old future is explicitly discarded. When preserve_suffix
    is true, every later choice must replay successfully, atomically; invalid
    suffixes fail closed rather than being silently truncated. The original
    source, history, and any on-disk save are never changed.
    """
    if authorized is not True:
        raise PermissionError("dialogue fork requires operator authorization")
    if (type(actions) is not list or not 1 <= len(actions) <= MAX_FORK_ACTIONS
            or type(checkpoint_index) is not int
            or not 0 <= checkpoint_index < len(actions)
            or type(alternative) is not str or not 1 <= len(alternative) <= 256
            or alternative != alternative.strip()
            or any(ord(ch) < 32 for ch in alternative)
            or not _lease(expected_session_digest)
            or type(preserve_suffix) is not bool):
        raise StudioQuestError("invalid dialogue fork checkpoint or lease")
    if expected_source_digest is not None and not _lease(expected_source_digest):
        raise StudioQuestError("invalid dialogue fork source lease")
    before = replay_quest(documents, actions, authorized=True)
    if before.digest != expected_session_digest:
        raise StudioQuestError("stale dialogue fork session lease")
    original = [list(pair) for pair in before.choices]
    stage_id, old_alternative = original[checkpoint_index]
    if old_alternative == alternative:
        raise StudioQuestError("dialogue fork must select a different authored choice")
    prefix = original[:checkpoint_index]
    preview = preview_dialogue_choices(
        documents, prefix, authorized=True,
        expected_source_digest=expected_source_digest)
    candidates = [
        item for item in preview["previews"]
        if item["quest_stage"] == stage_id and item["alternative"] == alternative
    ]
    if len(candidates) != 1:
        raise StudioQuestError("dialogue fork choice is unavailable or ambiguous")
    chosen = candidates[0]
    committed = commit_dialogue_choice(
        documents, prefix, stage_id=stage_id, alternative=alternative,
        expected_preview_digest=chosen["preview_digest"], authorized=True,
        expected_source_digest=preview["source_digest"])
    suffix = original[checkpoint_index + 1:]
    new_actions = prefix + [[stage_id, alternative]]
    if preserve_suffix:
        new_actions += suffix
    after = replay_quest(documents, new_actions, authorized=True)
    if (committed["session_digest"] !=
            replay_quest(documents, new_actions[:checkpoint_index + 1],
                         authorized=True).digest):
        raise StudioQuestError("dialogue fork optimistic commitment drift")
    if (before.project_id != after.project_id
            or before.source_digest != after.source_digest
            or committed["source_digest"] != preview["source_digest"]):
        raise StudioQuestError("dialogue fork source drift")
    staged = compile_dialogue_staging(
        documents, new_actions, authorized=True,
        expected_source_digest=preview["source_digest"])
    if staged["session_digest"] != after.digest:
        raise StudioQuestError("dialogue fork staging replay mismatch")
    comparison = compare_dialogue_histories(
        documents, original, new_actions, authorized=True,
        expected_source_digest=preview["source_digest"])
    if (comparison["left_session_digest"] != before.digest
            or comparison["right_session_digest"] != after.digest
            or comparison["first_divergence_index"] != checkpoint_index):
        raise StudioQuestError("dialogue fork comparison mismatch")
    progress = quest_progress(after, documents)
    payload: dict[str, object] = {
        "schema": FORK_SCHEMA,
        "project_id": before.project_id,
        "source_digest": preview["source_digest"],
        "quest_source_digest": before.source_digest,
        "original_session_digest": before.digest,
        "session_digest": after.digest,
        "checkpoint_index": checkpoint_index,
        "quest_stage": stage_id,
        "previous_alternative": old_alternative,
        "replacement_alternative": alternative,
        "preserve_suffix": preserve_suffix,
        "discarded_suffix": [] if preserve_suffix else suffix,
        "preserved_suffix": suffix if preserve_suffix else [],
        "original_receipt": before.receipt(),
        "forked_receipt": after.receipt(),
        "progress": progress,
        "staging_after": staged,
        "comparison": comparison,
        "original_history_unchanged": True,
        "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["fork_digest"] = _digest(payload)
    return payload
