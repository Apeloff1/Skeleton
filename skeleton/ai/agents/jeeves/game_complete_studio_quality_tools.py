"""Authorized Jeeves Studio bridge for 27-plane game-production quality.

All source mapping, operator identity and native runtime witnesses come from
the trusted host. Existing StudioCommand + ToolRegistry authorizers enforce
individual invocation; this factory grants NO rights, callbacks or filesystem
capabilities by its own existence.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from skeleton.game.production_quality import QualityGateError
from skeleton.game.production_deep_gates import _sha
from skeleton.game.production_history import QualityHistoryStore
from skeleton.game.production_studio_gates import audit_complete_studio
from skeleton.game.production_studio_assurance import (
    challenge_studio_verifiers, compare_studio_reports, studio_repair_queue,
    inspect_native_game_witness,
)
from .game_studio_tools import StudioCommand


def complete_studio_quality_handlers(
    projects: Mapping[str, tuple[str, Callable[[], Mapping[str, Any]]]], *,
    store: QualityHistoryStore,
    operator_id: str,
    native_owners: Mapping[str, Callable[[], tuple]] | None = None,
    approve_patch: Callable[[StudioCommand, Mapping[str, Any]], bool] | None = None,
    verify_candidate: Callable[[StudioCommand, Mapping[str, Any]], bool] | None = None,
) -> dict[str, Callable[[StudioCommand, Any], dict]]:
    """Create eight concrete, host-backed operations for the existing registry."""
    if (not isinstance(projects, Mapping) or not projects or
            not isinstance(store, QualityHistoryStore) or
            type(operator_id) is not str or not 3 <= len(operator_id) <= 128
            or not operator_id.isascii() or
            not all(ch.isalnum() or ch in "._-" for ch in operator_id)):
        raise QualityGateError("original game project owners, journal and reviewer required")
    bound: dict[str, tuple[str, Callable]] = {}
    for key, item in projects.items():
        if (type(key) is not str or not 1 <= len(key) <= 128 or
                type(item) is not tuple or len(item) != 2 or
                not callable(item[1])):
            raise QualityGateError("project must be attached by trusted runtime host")
        bound[key] = (_sha(item[0], "host source SHA"), item[1])
    if native_owners is not None and (
            not isinstance(native_owners, Mapping) or
            any(key not in bound or not callable(provider)
                for key, provider in native_owners.items())):
        raise QualityGateError("host-controlled native evidence mapping invalid")
    native = dict(native_owners or {})
    if (approve_patch is None) != (verify_candidate is None):
        raise QualityGateError("repair preview requires both trusted host-review callbacks")
    if approve_patch is not None and (
            not callable(approve_patch) or not callable(verify_candidate)):
        raise QualityGateError("repair approval and source verification must be callable")

    def source(command: StudioCommand) -> Mapping:
        if not isinstance(command, StudioCommand) or command.project_id not in bound:
            raise QualityGateError("unauthorized source owner")
        digest, getter = bound[command.project_id]
        candidate = getter()
        if not isinstance(candidate, Mapping) or candidate.get("source_sha256") != digest:
            raise QualityGateError("host candidate changed source or is missing")
        return candidate

    def audit(command: StudioCommand, context: Any) -> dict:
        if command.payload:
            raise QualityGateError("source audit takes only its authorized original project")
        return audit_complete_studio(source(command))

    def dragon(command: StudioCommand, context: Any) -> dict:
        if command.payload:
            raise QualityGateError("Dragon challenge cannot change evidence scope")
        return challenge_studio_verifiers(source(command))

    def work(command: StudioCommand, context: Any) -> dict:
        limit = command.payload.get("limit", 256)
        if set(command.payload) - {"limit"} or type(limit) is not int:
            raise QualityGateError("work query accepts only bounded item limit")
        return studio_repair_queue(audit_complete_studio(source(command)), limit=limit)

    def diff(command: StudioCommand, context: Any) -> dict:
        if (set(command.payload) != {"prior_generation"} or
                type(command.payload["prior_generation"]) is not int):
            raise QualityGateError("historical comparison must select exact source generation")
        current = audit_complete_studio(source(command))
        previous = store.report_at(
            command.project_id, generation=command.payload["prior_generation"]
        )
        return compare_studio_reports(previous, current)

    def history(command: StudioCommand, context: Any) -> dict:
        source(command)
        limit = command.payload.get("limit", 64)
        if set(command.payload) - {"limit"} or type(limit) is not int:
            raise QualityGateError("history query accepts only bounded limit")
        return store.history(command.project_id, limit=limit)

    def record(command: StudioCommand, context: Any) -> dict:
        if (set(command.payload) != {"expected_generation", "expected_head"} or
                type(command.payload["expected_generation"]) is not int or
                type(command.payload["expected_head"]) is not str):
            raise QualityGateError("record action requires exact generation and CAS receipt")
        return store.append(
            command.project_id, audit_complete_studio(source(command)),
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    def review(command: StudioCommand, context: Any) -> dict:
        if set(command.payload) != {
            "decision", "reason_sha256", "report_head_sha256",
            "expected_generation", "expected_head",
        }:
            raise QualityGateError("candidate reviewer action requires exact CAS fields")
        source(command)
        return store.review(
            command.project_id, reviewer_id=operator_id,
            decision=command.payload["decision"],
            reason_sha256=command.payload["reason_sha256"],
            report_head_sha256=command.payload["report_head_sha256"],
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    def native_inspect(command: StudioCommand, context: Any) -> dict:
        if command.payload:
            raise QualityGateError("model cannot provide or forge native game evidence")
        candidate = source(command)
        if command.project_id not in native:
            raise QualityGateError("host has no real native engine evidence for project")
        value = native[command.project_id]()
        if not isinstance(value, tuple) or len(value) != 4:
            raise QualityGateError("host native witness must bind world/player/files/report")
        return inspect_native_game_witness(candidate, *value)

    def repair_preview(command: StudioCommand, context: Any) -> dict:
        from skeleton.game.production_studio_repair import preview_reviewed_studio_repairs
        if approve_patch is None or verify_candidate is None:
            raise QualityGateError("host has not installed an independently reviewed editor")
        if set(command.payload) != {"patches"}:
            raise QualityGateError("preview requires an exact candidate patch list")
        patches = command.payload["patches"]
        if type(patches) is not list or len(patches) > 16:
            raise QualityGateError("bounded source edit requests only")
        result = preview_reviewed_studio_repairs(
            source(command), patches,
            authorize=lambda patch: approve_patch(command, patch),
            independently_verify=lambda new: verify_candidate(command, new),
        )
        return {
            "schema": result["schema"],
            "source_sha256": result["source_sha256"],
            "attempt_count": result["attempt_count"],
            "accepted_count": result["accepted_count"],
            "attempts": result["attempts"],
            "proposed_source_sha256": _sha(result["post_quality"]["source_digest"],
                                           "reviewed original source"),
            "quality_evidence_sha256": result["post_quality"]["evidence_digest"],
            "remaining_findings": len(result["post_quality"]["findings"]),
            "persisted": False,
            "release_approved": False,
            "receipt_digest": result["receipt_digest"],
        }

    return {
        "game.studio.quality.audit": audit,
        "game.studio.quality.dragon": dragon,
        "game.studio.quality.work": work,
        "game.studio.quality.diff": diff,
        "game.studio.quality.history": history,
        "game.studio.quality.record": record,
        "game.studio.quality.review": review,
        "game.studio.quality.native.inspect": native_inspect,
        **({"game.studio.quality.repair.preview": repair_preview}
           if approve_patch is not None else {}),
    }
