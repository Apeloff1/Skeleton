"""Host-authorized Jeeves bridge to the 84-plane original-game quality system."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from skeleton.game.production_quality import QualityGateError
from skeleton.game.production_deep_gates import _sha
from skeleton.game.production_history import QualityHistoryStore
from skeleton.game.production_expanded_gates import audit_expanded_studio
from skeleton.game.production_expanded_assurance import (
    queue_84, impact_84, compare_84,
)
from skeleton.game.production_expanded_dragon import challenge_84_verifiers
from .game_advanced_studio_quality_tools import advanced_studio_quality_handlers
from .game_studio_tools import StudioCommand


def expanded_studio_quality_handlers(
    projects: Mapping[str, tuple[str, Callable[[], Mapping[str, Any]]]], *,
    store: QualityHistoryStore,
    operator_id: str,
) -> dict[str, Callable[[StudioCommand, Any], dict]]:
    """Add eight host-backed operations without any new execution authority."""
    # Reuse existing host source owner and identity validation.
    advanced_studio_quality_handlers(projects, store=store, operator_id=operator_id)
    owned = {key: (_sha(info[0], "trusted source"), info[1])
             for key, info in projects.items()}

    def source(command: StudioCommand) -> Mapping:
        if not isinstance(command, StudioCommand) or command.project_id not in owned:
            raise QualityGateError("unauthorized original game")
        expected, reader = owned[command.project_id]
        value = reader()
        if not isinstance(value, Mapping) or value.get("source_sha256") != expected:
            raise QualityGateError("host source identity mismatch")
        return value

    def audit(command: StudioCommand, _context: Any) -> dict:
        if command.payload:
            raise QualityGateError("source report cannot be overridden by model payload")
        return audit_expanded_studio(source(command))

    def challenge(command: StudioCommand, _context: Any) -> dict:
        if command.payload:
            raise QualityGateError("Dragon challenge never accepts model evidence")
        return challenge_84_verifiers(source(command))

    def work(command: StudioCommand, _context: Any) -> dict:
        if set(command.payload) - {"limit"}:
            raise QualityGateError("invalid work filter")
        limit = command.payload.get("limit", 256)
        if type(limit) is not int:
            raise QualityGateError("work limit must be integer")
        return queue_84(audit_expanded_studio(source(command)), limit=limit)

    def impact(command: StudioCommand, _context: Any) -> dict:
        if command.payload:
            raise QualityGateError("impact graph requires only current source")
        return impact_84(audit_expanded_studio(source(command)))

    def history(command: StudioCommand, _context: Any) -> dict:
        source(command)
        if set(command.payload) - {"limit"}:
            raise QualityGateError("history supports only bounded limit")
        limit = command.payload.get("limit", 64)
        if type(limit) is not int:
            raise QualityGateError("history limit must be integer")
        return store.history(command.project_id, limit=limit)

    def diff(command: StudioCommand, _context: Any) -> dict:
        if (set(command.payload) != {"prior_generation"}
                or type(command.payload["prior_generation"]) is not int):
            raise QualityGateError("diff requires exact historical generation")
        current = audit_expanded_studio(source(command))
        previous = store.report_at(command.project_id,
                                   generation=command.payload["prior_generation"])
        return compare_84(previous, current)

    def record(command: StudioCommand, _context: Any) -> dict:
        if (set(command.payload) != {"expected_generation", "expected_head"}
                or type(command.payload["expected_generation"]) is not int
                or type(command.payload["expected_head"]) is not str):
            raise QualityGateError("journal append requires exact CAS generation and head")
        return store.append(
            command.project_id, audit_expanded_studio(source(command)),
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    def review(command: StudioCommand, _context: Any) -> dict:
        if set(command.payload) != {
            "decision", "reason_sha256", "report_head_sha256",
            "expected_generation", "expected_head",
        }:
            raise QualityGateError("host reviewer requires exact CAS and decision fields")
        source(command)
        return store.review(
            command.project_id, reviewer_id=operator_id,
            decision=command.payload["decision"],
            reason_sha256=command.payload["reason_sha256"],
            report_head_sha256=command.payload["report_head_sha256"],
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    return {
        "game.studio.expanded.audit": audit,
        "game.studio.expanded.challenge": challenge,
        "game.studio.expanded.work": work,
        "game.studio.expanded.impact": impact,
        "game.studio.expanded.diff": diff,
        "game.studio.expanded.history": history,
        "game.studio.expanded.record": record,
        "game.studio.expanded.review": review,
    }
