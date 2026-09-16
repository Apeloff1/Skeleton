"""Deterministic four-agent squad selection for the 1,000-role Studio.

The logical fleet remains large, but one engineering task activates exactly four
independent responsibilities: scout/research, builder/lead, reviewer, tester/
verifier. This module contains no model calls or repository mutation; it is a
reusable scheduling primitive for Night, Idle, and Autonomous Studio runtimes.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.shift_supervisor.prompts import compose_role_prompt

from .studio_registry import StudioBot, find_specialist


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


def select_task_squad(division: str, *, seed: str) -> StudioTaskSquad:
    """Select one stable four-agent squad for a task/seed pair."""
    division = str(division).strip()
    seed = str(seed).strip()
    if not division:
        raise ValueError("division is required")
    if not seed:
        raise ValueError("seed is required")

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
