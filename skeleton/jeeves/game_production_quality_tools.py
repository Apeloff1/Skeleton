"""Host-authorized Jeeves Studio quality operations for canonical game projects.

Read-only audit/challenge/plan/inspect/history and explicit operator-accepted
persistence share the existing register_studio_tools authorization boundary.
There is no autonomous rights approval or native Godot substitution.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from skeleton.game.production_deep_gates import audit_deep_candidate, _sha
from skeleton.game.production_dragon_redteam import challenge_quality_verifiers
from skeleton.game.production_history import QualityHistoryStore
from skeleton.game.production_quality import QualityGateError
from skeleton.game.production_repair import suggest_quality_repairs

from .game_studio_tools import StudioCommand

READ_OPERATIONS = (
    "game.quality.audit", "game.quality.inspect", "game.quality.history",
    "game.quality.challenge", "game.quality.repair.plan",
)
WRITE_OPERATIONS = ("game.quality.record",)


def game_quality_studio_handlers(
    sources: Mapping[str, tuple[str, Callable[[], Mapping[str, Any]]]], *,
    store: QualityHistoryStore,
) -> dict[str, Callable[[StudioCommand, Any], dict]]:
    """Factory admits only host-installed original game sources and journal."""
    if (not isinstance(sources, Mapping) or not sources or
            not isinstance(store, QualityHistoryStore)):
        raise QualityGateError("host game owner mapping and audit journal required")
    installed = {}
    for name, spec in sources.items():
        if (type(name) is not str or not 1 <= len(name) <= 128 or
                type(spec) is not tuple or len(spec) != 2 or
                not callable(spec[1])):
            raise QualityGateError("source project needs trusted host audit adapter")
        installed[name] = (_sha(spec[0], "host project source"), spec[1])

    def owner(command: StudioCommand) -> tuple[str, Callable]:
        if not isinstance(command, StudioCommand) or command.project_id not in installed:
            raise QualityGateError("unowned or unregistered project")
        return installed[command.project_id]

    def current(command: StudioCommand) -> dict:
        source, provider = owner(command)
        value = provider()
        if not isinstance(value, Mapping) or value.get("source_sha256") != source:
            raise QualityGateError("current game project source changed or is unavailable")
        result = audit_deep_candidate(value)
        if result["source_digest"] != source:
            raise QualityGateError("quality audit source mismatch")
        return result

    def audit(command, context) -> dict:
        return current(command)

    def inspect(command, context) -> dict:
        owner(command)
        return store.inspect(command.project_id)

    def history(command, context) -> dict:
        owner(command)
        limit = command.payload.get("limit", 32)
        if type(limit) is not int:
            raise QualityGateError("quality history limit must be integer")
        return store.history(command.project_id, limit=limit)

    def challenge(command, context) -> dict:
        source, provider = owner(command)
        candidate = provider()
        if not isinstance(candidate, Mapping) or candidate.get("source_sha256") != source:
            raise QualityGateError("Dragon red team cannot inspect foreign game source")
        return challenge_quality_verifiers(candidate)

    def repair_plan(command, context) -> dict:
        return suggest_quality_repairs(current(command))

    def record(command, context) -> dict:
        if (set(command.payload) != {"expected_generation", "expected_head"} or
                type(command.payload["expected_generation"]) is not int or
                type(command.payload["expected_head"]) is not str):
            raise QualityGateError("quality record requires exact persisted CAS")
        report = current(command)
        return store.append(
            command.project_id, report,
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    return {
        "game.quality.audit": audit,
        "game.quality.inspect": inspect,
        "game.quality.history": history,
        "game.quality.challenge": challenge,
        "game.quality.repair.plan": repair_plan,
        "game.quality.record": record,
    }


def frontier_quality_studio_handlers(
    sources: Mapping[str, tuple[str, Callable[[], Mapping[str, Any]]]], *,
    store: QualityHistoryStore,
    reviewer_id: str,
    integrity_key_id: str | None = None,
    integrity_key: bytes | None = None,
) -> dict[str, Callable[[StudioCommand, Any], dict]]:
    """Host-owned frontier quality workflow; uses existing exact-command grant.

    Source adapters, operator identity and any HMAC secret are passed by the
    trusted runtime, NEVER recovered from model arguments. Every mutation is a
    separate `studio_execute` tool action requiring the host authorizer.
    """
    from skeleton.game.production_frontier_gates import audit_frontier_candidate
    from skeleton.game.production_frontier_assurance import (
        challenge_frontier_verifiers, host_attest_report,
        prioritized_quality_work, quality_report_delta,
    )
    if (not isinstance(sources, Mapping) or not sources or
            not isinstance(store, QualityHistoryStore) or
            type(reviewer_id) is not str or not 3 <= len(reviewer_id) <= 128 or
            not reviewer_id.isascii() or
            any(not (ch.isalnum() or ch in "._-") for ch in reviewer_id)):
        raise QualityGateError("frontier studio requires host owners and named reviewer")
    if (integrity_key is None) != (integrity_key_id is None):
        raise QualityGateError("integrity key and host key identity must be supplied together")
    if integrity_key is not None and (type(integrity_key) is not bytes or
                                      not 32 <= len(integrity_key) <= 4096):
        raise QualityGateError("host integrity secret invalid")
    approved = {}
    for name, entry in sources.items():
        if (type(name) is not str or not 1 <= len(name) <= 128 or
                type(entry) is not tuple or len(entry) != 2 or
                not callable(entry[1])):
            raise QualityGateError("invalid host-owned frontier game source")
        approved[name] = (_sha(entry[0], "host game source"), entry[1])

    def source(command: StudioCommand) -> Mapping:
        if not isinstance(command, StudioCommand) or command.project_id not in approved:
            raise QualityGateError("unowned quality frontier project")
        expected, callback = approved[command.project_id]
        result = callback()
        if not isinstance(result, Mapping) or result.get("source_sha256") != expected:
            raise QualityGateError("host supplied stale or foreign game source")
        return result

    def audit(command: StudioCommand, context) -> dict:
        return audit_frontier_candidate(source(command))

    def work(command: StudioCommand, context) -> dict:
        limit = command.payload.get("limit", 64)
        if type(limit) is not int:
            raise QualityGateError("bounded work queue limit expected")
        return prioritized_quality_work(audit(command, context), limit=limit)

    def challenge(command: StudioCommand, context) -> dict:
        return challenge_frontier_verifiers(source(command))

    def diff(command: StudioCommand, context) -> dict:
        source(command)
        generation = command.payload.get("previous_generation")
        if type(generation) is not int:
            raise QualityGateError("historical comparison needs exact generation")
        old = store.report_at(command.project_id, generation=generation)
        return quality_report_delta(old, audit(command, context))

    def reviews_inspect(command: StudioCommand, context) -> dict:
        source(command)
        limit = command.payload.get("limit", 64)
        if type(limit) is not int:
            raise QualityGateError("bounded review query required")
        return store.inspect_reviews(command.project_id, limit=limit)

    def record(command: StudioCommand, context) -> dict:
        if (set(command.payload) != {"expected_generation", "expected_head"}
                or type(command.payload["expected_generation"]) is not int
                or type(command.payload["expected_head"]) is not str):
            raise QualityGateError("record requires generation and source audit lease")
        result = audit(command, context)
        return store.append(
            command.project_id, result,
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    def review(command: StudioCommand, context) -> dict:
        required = {"decision", "reason_sha256", "report_head_sha256",
                    "expected_generation", "expected_head"}
        if set(command.payload) != required:
            raise QualityGateError("operator decision requires immutable evidence and CAS fields")
        source(command)
        return store.review(
            command.project_id,
            reviewer_id=reviewer_id,
            decision=command.payload["decision"],
            reason_sha256=command.payload["reason_sha256"],
            report_head_sha256=command.payload["report_head_sha256"],
            expected_generation=command.payload["expected_generation"],
            expected_head=command.payload["expected_head"],
        )

    def attest(command: StudioCommand, context) -> dict:
        if command.payload:
            raise QualityGateError("integrity secret and reviewer identity are host-owned")
        if integrity_key is None or integrity_key_id is None:
            raise QualityGateError("host integrity key unavailable; no fabricated attestation")
        return host_attest_report(audit(command, context),
                                  host_secret=integrity_key,
                                  key_id=integrity_key_id,
                                  reviewer_id=reviewer_id)

    return {
        "game.quality.frontier.audit": audit,
        "game.quality.frontier.work": work,
        "game.quality.frontier.challenge": challenge,
        "game.quality.frontier.diff": diff,
        "game.quality.frontier.reviews.inspect": reviews_inspect,
        "game.quality.frontier.record": record,
        "game.quality.frontier.review": review,
        "game.quality.frontier.attest": attest,
    }
