"""Atomic economy-guarded player choices against canonical saved sessions.

The canonical session trace and reviewed economy are checked under the same
world-wide exclusive lease before publication. This is an opt-in operator path;
it does not silently change or weaken the core SessionStore contract.
"""
from __future__ import annotations

import os
from typing import Any

from .economy import (
    EconomyStore, _advance, _graph, replay_economy, validate_economy,
)
from .session import SessionStore, apply_choice, validate_session
from .world_canon import CanonError, _id, canonical, digest, strict_json


def economy_player_view(source: Any, world: Any, session: Any) -> dict[str, Any]:
    validate_session(session, world)
    validate_economy(source, world)
    if source["approved"] is not True:
        raise CanonError("economy_review_required")
    replay = replay_economy(source, world, session["choices"])
    data, resource_ids, capacities, effects, edges = _graph(source, world)
    balances = tuple(replay["balances"][rid] for rid in resource_ids)
    flags = set(replay["flags"])
    options = []
    if not replay["ending"]:
        for edge in edges.get(replay["scene"], []):
            if set(edge["requires"]) <= flags and _advance(
                    edge, balances, resource_ids, capacities, effects) is not None:
                options.append({
                    "id": edge["id"], "label": edge["label"], "to": edge["to"],
                })
    return {
        "schema": "jeeves.world.economy_player.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "economy_digest": digest(source),
        "session_digest": digest(session), "revision": session["revision"],
        "replay": replay, "available_choices": options,
        "qualification": "reviewed_source_replay_not_device_certified",
    }


class EconomySessionStore:
    """Fail-closed choice admission with expected economy and session leases."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.economy = EconomyStore(root)

    def choose(self, world_id: str, slot: str, choice_id: str, *,
               expected_session_digest: str,
               expected_economy_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        _id(slot, "slot")
        _id(choice_id, "choice_id")
        fd = self.economy.worlds._directory()
        try:
            self.economy._lock(fd, world_id)
            try:
                world = self.economy._world(fd, world_id)
                source = self.economy._source(fd, world_id, world)
                if digest(source) != expected_economy_digest:
                    raise CanonError("economy_stale_source")
                if source["approved"] is not True:
                    raise CanonError("economy_review_required")
                session_name = SessionStore._name(world_id, slot)
                session = validate_session(
                    strict_json(self.economy.worlds._read(fd, session_name)), world)
                if digest(session) != expected_session_digest:
                    raise CanonError("economy_stale_session")
                updated = apply_choice(session, world, choice_id)
                # No write is possible unless the entire new trace is affordable.
                replay_economy(source, world, updated["choices"])
                self.economy.worlds._write(fd, session_name, canonical(updated))
                return economy_player_view(source, world, updated)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
