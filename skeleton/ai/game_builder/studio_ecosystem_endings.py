"""Report which original studio endings are truly bound to sandbox mechanics.

Authored names, wishes, and branch briefs never create evidence tokens. An
unbound ending stays explicitly unsupported even if prose promises it.
"""
from __future__ import annotations

from typing import Any, Mapping
from .studio_ecosystem_quest import (
    QuestSession, compile_quest_program, verify_quest_session,
)


def ending_obligations(documents: Mapping[str, Any],
                       session: QuestSession | None = None) -> dict[str, object]:
    program = compile_quest_program(documents)
    earned: set[str] = set()
    if session is not None:
        verify_quest_session(session, documents, program=program)
        earned = set(session.completed) | {
            stage.reward for stage in program.stages if stage.key in session.completed
        }
    internally_possible = set(program.stage_ids) | {s.reward for s in program.stages}
    statuses = []
    for key, required in program.endings:
        missing_bindings = sorted(set(required) - internally_possible)
        unmet = sorted(set(required) - earned)
        statuses.append({"ending_id": key, "required": list(required),
                         "missing_mechanic_bindings": missing_bindings,
                         "unmet_in_session": unmet,
                         "sandbox_eligible": not unmet,
                         "physical_or_rights_evidence_verified": False})
    return {
        "schema": "skeleton.game_builder.studio_ending_obligations.v1",
        "project_id": program.project_id, "source_digest": program.source_digest,
        "session_digest": session.digest if session else None,
        "endings": statuses,
        "all_endings_mechanically_bound": all(
            not r["missing_mechanic_bindings"] for r in statuses
        ), "native_ending_delivery_verified": False, "release_certified": False,
    }
