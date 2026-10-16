"""Non-destructive branching and action evidence for original Director games.

Forks are *new, create-only journals* replayed from an approved source session.
They do not alter original saves, scripts, assets or historical scene receipts.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import DirectorAction, director_initial, director_step
from skeleton.developer.jeeves_game_director_session import (
    _create, _folder, _hash, _load, _read_doc, _view, EVENT_SCHEMA,
    NAME,
)

SCHEMA = "skeleton.jeeves.director_fork.v1"


def trace(root: Path, *, session: str, tail: int = 64) -> dict[str, Any]:
    """Return a bounded view of independently replay-verified action history."""
    if type(tail) is not int or not 1 <= tail <= 512:
        raise ValueError("--tail must be 1..512 recorded actions")
    folder, world, state, manifest, head, count = _load(root, name=session)
    recent = [
        _read_doc(folder / f"{index:08d}.json")
        for index in range(max(1, count - tail + 1), count + 1)
    ]
    return {
        "ok": True, "schema": SCHEMA, "action": "director-session-trace",
        "session": session, "project": world.project_id,
        "source_sha256": manifest["source_sha256"],
        "director_world_sha256": world.digest,
        "head_sha256": head, "sequence": count,
        "final_state_sha256": state.digest,
        "recent_actions": [
            {"sequence": item["sequence"], "action": item["action"],
             "before_sha256": item["before_sha256"],
             "after_sha256": item["after_sha256"],
             "receipt_sha256": item["receipt_sha256"]}
            for item in recent
        ],
        "recorded_timeline_complete": len(recent) == count,
        "fork_origin": manifest.get("fork_origin"),
        "native_save_file_verified": False,
    }


def fork(root: Path, *, session: str, new_session: str, at: int,
         approved_head: str | None) -> dict[str, Any]:
    """Fork an earlier choice with fresh integrity-linked receipts and lineage."""
    if not isinstance(new_session, str) or NAME.fullmatch(new_session) is None:
        raise ValueError("--other-session must be a new lowercase safe session")
    if new_session == session:
        raise ValueError("fork must create a new independent Director session")
    parent_folder, world, current, original, head, count = _load(root, name=session)
    if type(at) is not int or not 0 <= at <= count:
        raise ValueError("fork point must be an existing recorded action sequence")
    if approved_head != head:
        raise ValueError("session changed or missing explicit --approve original journal head")
    # The new manifest must retain exact world and source identity. Its name is
    # different, so rehash every derived action receipt to prevent lineage fraud.
    manifest = {key: value for key, value in original.items() if key != "receipt_sha256"}
    manifest["name"] = new_session
    manifest["fork_origin"] = {
        "parent_session": session, "parent_head_sha256": head, "fork_sequence": at,
    }
    manifest["receipt_sha256"] = _hash(manifest)
    prior = manifest["receipt_sha256"]
    state = director_initial(world)
    parent = parent_folder.parent
    destination = parent / new_session
    if destination.is_symlink() or destination.exists():
        raise ValueError("fork destination exists; never overwrite a session")
    # The stage directory is private until publication; no consumer may load a
    # partially constructed branch. A concurrent writer must not be allowed to
    # change the parent journal head during this operation.
    stage = Path(tempfile.mkdtemp(prefix=".director-fork-", dir=parent))
    try:
        _create(stage / "00000000.json", manifest)
        for index in range(1, at + 1):
            source_event = _read_doc(parent_folder / f"{index:08d}.json")
            if source_event["before_sha256"] != state.digest:
                raise ValueError("fork source action previous state diverged")
            action = DirectorAction(**source_event["action"])
            state = director_step(world, state, action)
            if state.digest != source_event["after_sha256"]:
                raise ValueError("fork action replay diverged from original Director state")
            event = {
                "schema": EVENT_SCHEMA, "sequence": index,
                "prior_sha256": prior, "action": action.payload(),
                "before_sha256": source_event["before_sha256"],
                "after_sha256": source_event["after_sha256"],
            }
            event["receipt_sha256"] = _hash(event)
            _create(stage / f"{index:08d}.json", event)
            prior = event["receipt_sha256"]
        if at == count and state.digest != current.digest:
            raise ValueError("fork did not reproduce original end state")
        # Revalidate original head/contents immediately before publishing.
        _, live_world, live_state, _, live_head, live_count = _load(root, name=session)
        if (live_head != head or live_count != count
                or live_world.digest != world.digest or live_state.digest != current.digest):
            raise ValueError("original Director journal changed during branch construction")
        if destination.exists() or destination.is_symlink():
            raise ValueError("branch name was claimed during replay")
        os.rename(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    _, checked_world, checked_state, _, checked_head, checked_count = _load(
        root, name=new_session
    )
    if (checked_world.digest != world.digest or checked_state != state
            or checked_count != at or checked_head != prior):
        raise ValueError("published Director branch was not independently reproducible")
    return {
        "ok": True, "schema": SCHEMA, "action": "director-session-fork",
        "parent_session": session, "parent_head_sha256": head,
        "fork_sequence": at, "new_session": new_session,
        "fork_head_sha256": prior, "director_world_sha256": world.digest,
        "state_sha256": checked_state.digest,
        "copy_of_action_history_through_fork": True,
        "parent_modified": False, "native_engine_save_verified": False,
        "next_actions": [a["choice"] for a in _view(
            world, checked_state, name=new_session, sequence=at,
            last_sha=prior
        )["actions"]],
    }
