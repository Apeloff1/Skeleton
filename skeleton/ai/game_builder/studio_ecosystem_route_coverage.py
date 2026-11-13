"""Bounded executable alternate-route exploration for authored studio quests.

Enumerates legal player choices through a canonical topological quest order.
This measures simulated decision branches, not cinematic, native-gameplay,
actual external evidence, or automatically verified narrative endings.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress,
    start_quest, step_quest, verify_quest_session,
)


def explore_quest_routes(documents: Mapping[str, Any], *, authorized: bool,
                         max_terminal_routes: int = 256,
                         max_state_visits: int = 4096) -> dict[str, object]:
    if not authorized:
        raise PermissionError("route exploration requires operator authorization")
    if (type(max_terminal_routes) is not int or not 1 <= max_terminal_routes <= 4096
            or type(max_state_visits) is not int or not 1 <= max_state_visits <= 65536):
        raise StudioQuestError("invalid route exploration resource budget")
    program = compile_quest_program(documents)
    queue = deque([start_quest(documents, authorized=True)])
    terminal_digests = []
    endings: set[str] = set()
    visits = 0
    sample = None
    frontier_truncated = False
    while queue and len(terminal_digests) < max_terminal_routes and visits < max_state_visits:
        session = queue.popleft()
        visits += 1
        if len(session.completed) == len(program.stages):
            verify_quest_session(session, documents)
            status = quest_progress(session, documents)
            terminal_digests.append(session.digest)
            endings.update(status["sandbox_endings_eligible"])
            if sample is None:
                sample = session.receipt()
            continue
        # Canonical topological order avoids falsely counting equivalent
        # independent-stage permutations as distinct story routes.
        stage = program.stages[len(session.completed)]
        for alternative in stage.alternatives:
            if len(queue) >= max_state_visits:
                frontier_truncated = True
                break
            queue.append(step_quest(session, documents, stage=stage.key,
                                    alternative=alternative, authorized=True))
        if frontier_truncated:
            break
    complete = not queue and not frontier_truncated
    # Explicitly identify when a budget truncates the search frontier.
    return {
        "schema": "skeleton.game_builder.studio_quest_route_coverage.v1",
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "stage_count": len(program.stages),
        "state_visits": visits,
        "terminal_routes_examined": len(terminal_digests),
        "unique_terminal_routes": len(set(terminal_digests)),
        "sandbox_ending_ids_eligible": sorted(endings),
        "sample_replay": sample,
        "coverage_complete": complete,
        "truncated_by_resource_budget": not complete,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
