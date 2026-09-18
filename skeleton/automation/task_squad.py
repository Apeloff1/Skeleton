"""Deterministic four-agent squad selection for the 1,000-role Studio.

The logical fleet remains large, but one engineering task activates exactly four
independent responsibilities: scout/research, builder/lead, reviewer, tester/
verifier. This module contains no model calls or repository mutation; it is a
reusable scheduling primitive for Night, Idle, and Autonomous Studio runtimes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from threading import Lock
from typing import Any, Mapping

from core.shift_supervisor.prompts import compose_role_prompt

from .studio_registry import STUDIO, StudioBot, find_specialist

# Evidence-only roles may not author a patch or mutate canonical plan/lease state.
_EVIDENCE_ONLY_FORBIDDEN = frozenset(
    {
        "patch",
        "files",
        "diff",
        "plan_items",
        "plan_generation",
        "owner",
        "squad_lease",
        "lease_generation",
    }
)


@dataclass(frozen=True, slots=True)
class StudioTaskSquad:
    squad_key: str
    division: str
    researcher: StudioBot
    lead: StudioBot
    reviewer: StudioBot
    verifier: StudioBot

    @property
    def worker_ids(self) -> tuple[str, str, str, str]:
        return (
            self.researcher.bot_id,
            self.lead.bot_id,
            self.reviewer.bot_id,
            self.verifier.bot_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "squad_key": self.squad_key,
            "division": self.division,
            "researcher": self.researcher.to_dict(),
            "lead": self.lead.to_dict(),
            "reviewer": self.reviewer.to_dict(),
            "verifier": self.verifier.to_dict(),
        }


_ALLOCATION_LOCK = Lock()
_SCOPED_SQUADS: dict[tuple[str, str, str], StudioTaskSquad] = {}
_SCOPED_WORKERS: dict[str, set[str]] = {}


def _allocation_scope() -> str:
    """Return the explicit/process run scope used to prevent worker overload."""

    return os.getenv("STUDIO_SQUAD_SCOPE", "").strip() or os.getenv("GITHUB_RUN_ID", "").strip()


def _find_unreserved_specialist(
    division: str,
    *,
    mode: str,
    seed: str,
    reserved: set[str],
) -> StudioBot:
    matches = [
        bot
        for bot in STUDIO
        if bot.division == division and bot.mode == mode and bot.bot_id not in reserved
    ]
    if not matches:
        raise RuntimeError(
            f"no unreserved {mode!r} specialist remains in division {division!r} for this run"
        )
    return min(
        matches,
        key=lambda bot: hashlib.sha256(f"{seed}\x1f{bot.bot_id}".encode("utf-8")).digest(),
    )


def select_task_squad(division: str, *, seed: str) -> StudioTaskSquad:
    """Select one stable four-agent squad for a task/seed pair.

    When a run scope is present (``STUDIO_SQUAD_SCOPE`` or GitHub's
    ``GITHUB_RUN_ID``), workers are reserved for the lifetime of the process so
    different tasks cannot overload the same virtual worker. Re-selecting the
    same scoped task returns its original squad.
    """

    division = str(division).strip()
    seed = str(seed).strip()
    if not division:
        raise ValueError("division is required")
    if not seed:
        raise ValueError("seed is required")

    scope = _allocation_scope()
    if not scope:
        researcher = find_specialist(division, mode="scout", seed=f"{seed}:research")
        lead = find_specialist(division, mode="builder", seed=f"{seed}:lead")
        reviewer = find_specialist(division, mode="reviewer", seed=f"{seed}:review")
        verifier = find_specialist(division, mode="tester", seed=f"{seed}:verify")
        squad = StudioTaskSquad(
            squad_key=f"{division}:{seed}",
            division=division,
            researcher=researcher,
            lead=lead,
            reviewer=reviewer,
            verifier=verifier,
        )
        if len(set(squad.worker_ids)) != 4:
            raise RuntimeError("task squad roles must map to four distinct workers")
        return squad

    cache_key = (scope, division, seed)
    with _ALLOCATION_LOCK:
        cached = _SCOPED_SQUADS.get(cache_key)
        if cached is not None:
            return cached

        reserved = set(_SCOPED_WORKERS.get(scope, set()))
        researcher = _find_unreserved_specialist(
            division,
            mode="scout",
            seed=f"{seed}:research",
            reserved=reserved,
        )
        reserved.add(researcher.bot_id)
        lead = _find_unreserved_specialist(
            division,
            mode="builder",
            seed=f"{seed}:lead",
            reserved=reserved,
        )
        reserved.add(lead.bot_id)
        reviewer = _find_unreserved_specialist(
            division,
            mode="reviewer",
            seed=f"{seed}:review",
            reserved=reserved,
        )
        reserved.add(reviewer.bot_id)
        verifier = _find_unreserved_specialist(
            division,
            mode="tester",
            seed=f"{seed}:verify",
            reserved=reserved,
        )
        reserved.add(verifier.bot_id)

        squad = StudioTaskSquad(
            squad_key=f"{division}:{seed}",
            division=division,
            researcher=researcher,
            lead=lead,
            reviewer=reviewer,
            verifier=verifier,
        )
        if len(set(squad.worker_ids)) != 4:
            raise RuntimeError("task squad roles must map to four distinct workers")

        _SCOPED_SQUADS[cache_key] = squad
        _SCOPED_WORKERS[scope] = reserved
        return squad


def reject_non_evidence_payload(role: str, payload: Mapping[str, Any]) -> None:
    """Fail closed if a non-lead role tries to author code or mutate plan state."""

    name = str(role).strip().lower()
    if name == "lead":
        return
    if name not in {"researcher", "reviewer", "verifier"}:
        raise KeyError(role)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} output must be an object")
    leaked = sorted(key for key in payload if str(key) in _EVIDENCE_ONLY_FORBIDDEN)
    if leaked:
        raise ValueError(
            f"{name} must remain evidence-only and must not mutate plan state; "
            f"unexpected keys: {', '.join(leaked)}"
        )


def role_prompt(
    squad: StudioTaskSquad,
    role: str,
    *,
    title: str,
    objective: str,
    allowed_paths: tuple[str, ...] = (),
) -> str:
    """Render the canonical organization role plus task-specific responsibility."""
    canonical = {
        "researcher": ("researcher", squad.researcher),
        "lead": ("lead", squad.lead),
        "reviewer": ("reviewer", squad.reviewer),
        "verifier": ("verifier", squad.verifier),
    }
    if role not in canonical:
        raise KeyError(role)
    contract_name, worker = canonical[role]
    paths = ", ".join(allowed_paths) if allowed_paths else "read-only evidence boundary supplied by runtime"
    detail = (
        f"Worker identity: {worker.bot_id} ({worker.division}/{worker.track}/{worker.mode}).\n"
        f"Task: {title}\nObjective: {objective}\nAllowed paths: {paths}\n"
        "Return only the structured output requested by the calling runtime. "
        "Do not recruit extra workers or bypass the canonical task lease."
    )
    return compose_role_prompt(contract_name, detail)