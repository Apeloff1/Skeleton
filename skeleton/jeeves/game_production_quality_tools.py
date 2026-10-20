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
