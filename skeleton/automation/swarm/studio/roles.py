"""Production roles for the game-studio swarm.

These roles sit on the canonical swarm DAG. They do not replace the kernel
agent roles (scout, worker, guardian, oracle). Each production role binds to
one of those roles for routing and publishes a handoff contract: the artefact
keys it must leave behind.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from skeleton.automation.swarm.roles import RoleRegistry
from skeleton.automation.swarm.types import AgentRole


class StudioRole(str, Enum):
    DIRECTOR = "director"
    DESIGNER = "designer"
    SYSTEMS = "systems"
    LEVEL = "level"
    NARRATIVE = "narrative"
    ART = "art"
    AUDIO = "audio"
    QA = "qa"


class StudioContractError(ValueError):
    """A role finished without the artefact its handoff contract requires."""


@dataclass(frozen=True)
class HandoffContract:
    role: StudioRole
    capability: str
    responsibility: str
    swarm_role: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]


STUDIO_ROLES: dict[StudioRole, HandoffContract] = {
    StudioRole.DIRECTOR: HandoffContract(
        StudioRole.DIRECTOR,
        "studio.director",
        "Turn the brief into pillars, constraints, and milestone gates.",
        "ORACLE",
        (),
        ("title", "pillar", "milestones"),
    ),
    StudioRole.DESIGNER: HandoffContract(
        StudioRole.DESIGNER,
        "studio.design",
        "Define the core loop, verbs, and win condition.",
        "SCOUT",
        ("title", "pillar"),
        ("core_loop", "verbs", "win", "fantasy"),
    ),
    StudioRole.SYSTEMS: HandoffContract(
        StudioRole.SYSTEMS,
        "studio.systems",
        "Specify the mechanics that implement the verbs.",
        "WORKER",
        ("verbs", "win"),
        ("mechanics", "verbs"),
    ),
    StudioRole.LEVEL: HandoffContract(
        StudioRole.LEVEL,
        "studio.level",
        "Lay out spaces, exits, and what the player finds there.",
        "SCOUT",
        ("verbs", "win"),
        ("rooms", "start_room"),
    ),
    StudioRole.NARRATIVE: HandoffContract(
        StudioRole.NARRATIVE,
        "studio.narrative",
        "Write the beats a player can actually reach.",
        "SCOUT",
        ("fantasy",),
        ("beats", "speaker"),
    ),
    StudioRole.ART: HandoffContract(
        StudioRole.ART,
        "studio.art",
        "Request only the assets the loop needs.",
        "WORKER",
        ("fantasy",),
        ("assets",),
    ),
    StudioRole.AUDIO: HandoffContract(
        StudioRole.AUDIO,
        "studio.audio",
        "List cues for the same loop beats.",
        "WORKER",
        ("core_loop",),
        ("cues",),
    ),
    StudioRole.QA: HandoffContract(
        StudioRole.QA,
        "studio.qa",
        "Score the Godot checker, core-loop marker, and headless boot, then file defects.",
        "GUARDIAN",
        ("schema_version",),
        ("summary", "passed"),
    ),
}


TASK_OUTPUTS: dict[str, tuple[str, ...]] = {
    contract.capability: contract.produces for contract in STUDIO_ROLES.values()
}
TASK_OUTPUTS["studio.repair"] = ("summary", "actions")


def production_role_registry() -> RoleRegistry:
    """Swarm role registry extended with studio capabilities."""
    registry = RoleRegistry()
    registry.register(AgentRole.ORACLE, ("prediction", "advisory", "studio.director"))
    registry.register(
        AgentRole.SCOUT,
        ("discovery", "information", "studio.design", "studio.narrative", "studio.level"),
    )
    registry.register(
        AgentRole.WORKER,
        (
            "execution",
            "computation",
            "studio.systems",
            "studio.art",
            "studio.audio",
            "studio.repair",
        ),
    )
    registry.register(AgentRole.GUARDIAN, ("validation", "fault-detection", "studio.qa"))
    return registry


def _present(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    if isinstance(value, bool):
        return True
    return isinstance(value, (int, float))


def validate_artefact(role: StudioRole, artefact: Mapping[str, object]) -> None:
    """Reject a handoff whose produced keys are missing or blank."""
    contract = STUDIO_ROLES[role]
    if not isinstance(artefact, Mapping):
        raise StudioContractError(f"{role.value} artefact must be an object")
    missing = [key for key in contract.produces if not _present(artefact.get(key))]
    if missing:
        raise StudioContractError(f"{role.value} missing {', '.join(missing)}")


def validate_capability_output(capability: str, artefact: Mapping[str, object]) -> None:
    expected = TASK_OUTPUTS.get(capability)
    if expected is None:
        raise StudioContractError(f"unknown capability {capability}")
    if not isinstance(artefact, Mapping):
        raise StudioContractError(f"{capability} artefact must be an object")
    missing = [key for key in expected if not _present(artefact.get(key))]
    if missing:
        raise StudioContractError(f"{capability} missing {', '.join(missing)}")
