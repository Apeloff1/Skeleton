"""Source-leased three-way merge of original offline story checkpoints.

All three browser receipts are hostile input. Their histories are replayed
against the current canonical quest source; the ancestor must be an exact
prefix of each fork. A merge never invents external evidence or overwrites a
player's checkpoint. Incompatible choices or order constraints fail closed.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
    verify_quest_session,
)
from .studio_ecosystem_story_review import (
    SCHEMA, _replay_browser_story_receipt,
)

MAX_MERGED_BYTES = 65536


def _subsequence(needle: tuple[tuple[str, str], ...],
                 haystack: tuple[tuple[str, str], ...]) -> bool:
    """Every fork's authored action order must survive the merged replay."""
    cursor = iter(haystack)
    return all(any(action == wanted for action in cursor) for wanted in needle)


def merge_browser_story_checkpoints(
    ancestor_raw: bytes, current_raw: bytes, candidate_raw: bytes,
    documents: Mapping[str, Any], *, authorized: bool,
) -> dict[str, object]:
    """Reconcile nonconflicting forks and return a new, unpersisted checkpoint.

    Stage actions in the common ancestor are immutable. Independent new
    stages are merged in source-topological order; conflicting selections
    and mutually incompatible ordering are rejected rather than guessed.
    """
    if authorized is not True:
        raise PermissionError("checkpoint merge requires operator authorization")
    program = compile_quest_program(documents)
    ancestor_program, ancestor = _replay_browser_story_receipt(
        ancestor_raw, documents, authorized=True)
    current_program, current = _replay_browser_story_receipt(
        current_raw, documents, authorized=True)
    candidate_program, candidate = _replay_browser_story_receipt(
        candidate_raw, documents, authorized=True)
    if any(item.source_digest != program.source_digest for item in (
            ancestor_program, current_program, candidate_program)):
        raise StudioQuestError("checkpoint merge source identity mismatch")
    prefix = ancestor.choices
    if (current.choices[:len(prefix)] != prefix
            or candidate.choices[:len(prefix)] != prefix):
        raise StudioQuestError("checkpoint fork does not extend the leased ancestor")
    proposed: dict[str, str] = dict(prefix)
    for stage, choice in current.choices[len(prefix):] + candidate.choices[len(prefix):]:
        existing = proposed.get(stage)
        if existing is not None and existing != choice:
            raise StudioQuestError("checkpoint forks conflict on an authored choice")
        proposed[stage] = choice
    # The ancestor's order is preserved verbatim. Later actions use the
    # authoritative topological order, never a browser-provided sort key.
    suffix = tuple((stage.key, proposed[stage.key]) for stage in program.stages
                   if stage.key in proposed and stage.key not in dict(prefix))
    merged_actions = prefix + suffix
    if (not _subsequence(current.choices, merged_actions)
            or not _subsequence(candidate.choices, merged_actions)):
        raise StudioQuestError("checkpoint forks have incompatible action order")
    merged = replay_quest(documents, merged_actions, authorized=True)
    verify_quest_session(merged, documents, program=program)
    progress = quest_progress(merged, documents)
    receipt = {
        "schema": SCHEMA,
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "choices": [list(pair) for pair in merged.choices],
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    # Browser-compatible, readable JSON; this is data for an explicit
    # operator save, not proof of a durable write or of release readiness.
    checkpoint = json.dumps(receipt, indent=2, ensure_ascii=True,
                            allow_nan=False)
    encoded = checkpoint.encode("utf-8")
    if not 1 <= len(encoded) <= MAX_MERGED_BYTES:
        raise StudioQuestError("merged checkpoint exceeds byte budget")
    # Re-parse the proposed checkpoint through the exact same hostile-input
    # gate to ensure exported data is independently replayable.
    _, roundtrip = _replay_browser_story_receipt(encoded, documents, authorized=True)
    if roundtrip != merged:
        raise StudioQuestError("merged checkpoint replay identity mismatch")
    return {
        "schema": "skeleton.game_builder.offline_story_checkpoint_merge.v1",
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "ancestor_session_digest": ancestor.digest,
        "current_session_digest": current.digest,
        "candidate_session_digest": candidate.digest,
        "merged_session_digest": merged.digest,
        "merged_checkpoint_sha256": sha256(encoded).hexdigest(),
        "merged_checkpoint": checkpoint,
        "merged_action_count": len(merged.choices),
        "new_actions_from_current": len(current.choices) - len(prefix),
        "new_actions_from_candidate": len(candidate.choices) - len(prefix),
        "sandbox_endings_eligible": progress["sandbox_endings_eligible"],
        "unmet_ending_predicates": progress["unmet_ending_predicates"],
        "ancestor_and_forks_unchanged": True,
        "replayed_from_authoritative_source": True,
        "persisted": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
