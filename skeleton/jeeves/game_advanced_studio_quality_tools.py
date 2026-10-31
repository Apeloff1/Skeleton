"""Host-scoped Jeeves operations for the seven advanced original-game quality gates.

This composes existing authorized StudioCommand and canonical SQLite owners.
The host must inject project loaders, journal and operator identity; no provider,
filesystem, editor, source or release authority follows from registration.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from skeleton.game.production_quality import QualityGateError
from skeleton.game.production_deep_gates import _sha
from skeleton.game.production_history import QualityHistoryStore
from skeleton.game.production_advanced_gates import audit_advanced_studio
from skeleton.game.production_advanced_assurance import (
    advanced_studio_work_queue, advanced_studio_impact_graph,
    challenge_advanced_studio, compare_advanced_studio_reports,
)
from .game_complete_studio_quality_tools import complete_studio_quality_handlers
from .game_studio_tools import StudioCommand


def advanced_studio_quality_handlers(
    projects: Mapping[str, tuple[str, Callable[[], Mapping[str, Any]]]], *,
    store: QualityHistoryStore,
    operator_id: str,
) -> dict[str, Callable[[StudioCommand, Any], dict]]:
    """Build eight host-bound read/write operations for the existing Jeeves registry."""
    # Reuse the existing host-bound owner and reviewer validation contract.
    complete_studio_quality_handlers(projects, store=store, operator_id=operator_id)
    owners = {key: (_sha(pair[0], "authorized project source"), pair[1])
              for key, pair in projects.items()}

    def candidate(command: StudioCommand) -> Mapping:
        if not isinstance(command, StudioCommand) or command.project_id not in owners:
            raise QualityGateError("no authorized original-game project owner")
        source_sha, get_source = owners[command.project_id]
        value = get_source()
        if not isinstance(value, Mapping) or value.get("source_sha256") != source_sha:
            raise QualityGateError("unbound host original-game source")
        return value

    def audit(command: StudioCommand, _context: Any) -> dict:
        if command.payload:
            raise QualityGateError("advanced audit must use exact host-owned source")
        return audit_advanced_studio(candidate(command))

    def dragon(command: StudioCommand, _context: Any) -> dict:
        if command.payload:
            raise QualityGateError("Dragon challenger does not accept source overrides")
        return challenge_advanced_studio(candidate(command))

    def work(command: StudioCommand, _context: Any) -> dict:
        if set(command.payload) - {"limit"}:
            raise QualityGateError("work query does not accept arbitrary arguments")
        limit = command.payload.get("limit", 256)
        if type(limit) is not int:
            raise QualityGateError("bounded work limit required")
        return advanced_studio_work_queue(audit_advanced_studio(candidate(command)), limit=limit)

    def impact(command: StudioCommand, _context: Any) -> dict:
        if command.payload:
            raise QualityGateError("impact graph is source-only")
        return advanced_studio_impact_graph(audit_advanced_studio(candidate(command)))

    def diff(command: StudioCommand, _context: Any) -> dict:
        if (set(command.payload) != {"prior_generation"} or
                type(command.payload["prior_generation"]) is not int):
            raise QualityGateError("compare requires exact historical generation")
        current = audit_advanced_studio(candidate(command))
        prior = store.report_at(command.project_id,
                                generation=command.payload["prior_generation"])
        return compare_advanced_studio_reports(prior, current)

    def history(command: StudioCommand, _context: Any) -> dict:
        candidate(command)
        if set(command.payload) - {"limit"}:
            raise QualityGateError("history accepts only bounded limit")
        limit = command.payload.get("limit", 64)
        if type(limit) is not int:
            raise QualityGateError("history limit is an integer")
        return store.history(command.project_id, limit=limit)

    def record(command: StudioCommand, _context: Any) -> dict:
        if (set(command.payload) != {"expected_generation", "expected_head"} or
                type(command.payload["expected_generation"]) is not int or
                type(command.payload["expected_head"]) is not str):
            raise QualityGateError("record requires journal generation and exact CAS head")
        return store.append(
            command.project_id, audit_advanced_studio(candidate(command)),
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    def review(command: StudioCommand, _context: Any) -> dict:
        if set(command.payload) != {
                "decision", "reason_sha256", "report_head_sha256",
                "expected_generation", "expected_head"}:
            raise QualityGateError("operator review requires exact CAS and decision")
        candidate(command)
        return store.review(
            command.project_id, reviewer_id=operator_id,
            decision=command.payload["decision"],
            reason_sha256=command.payload["reason_sha256"],
            report_head_sha256=command.payload["report_head_sha256"],
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    return {
        "game.studio.advanced.audit": audit,
        "game.studio.advanced.dragon": dragon,
        "game.studio.advanced.work": work,
        "game.studio.advanced.impact": impact,
        "game.studio.advanced.diff": diff,
        "game.studio.advanced.history": history,
        "game.studio.advanced.record": record,
        "game.studio.advanced.review": review,
    }
