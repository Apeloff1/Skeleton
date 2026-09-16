"""Reusable game-building guidance for AI-assisted game generation.

The game-specific generators in Skeleton can produce individual systems well,
but a collection of systems is not necessarily a playable game. This module
provides one deterministic skill that can be applied before generation and
used again as a validation gate for generated design briefs.

It intentionally has no model or engine dependency. Prompt builders, agents,
CLI tools, and API routes can all use the same requirements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

GAME_BUILDING_SECTION = "## Game-building requirements"

DEFAULT_GAME_BUILDING_REQUIREMENTS: tuple[str, ...] = (
    "Define the player goal and a repeatable core gameplay loop: observe, decide, act, receive feedback, progress.",
    "Make controls and the first meaningful player action discoverable without requiring external instructions.",
    "Define lifecycle states explicitly: start, active play, pause when supported, terminal state, and restart or retry.",
    "Define measurable win or progression conditions and loss or failure conditions so every run has a resolvable outcome.",
    "Scale challenge or progression deliberately and keep the initial state reachable, fair, and free of softlocks.",
    "Specify authoritative collision, bounds, resource, timing, and other gameplay rules wherever they affect outcomes.",
    "Provide immediate readable feedback for player actions, damage, rewards, errors, and important state changes.",
    "Expose enough HUD or status information for the player to make decisions without depending on hidden state.",
    "Use safe fallbacks for missing assets, invalid generated data, and unavailable optional systems instead of crashing.",
    "Finish with a compact playtest checklist covering start-to-finish completion, restart, edge cases, and target-runtime constraints.",
)

_REQUIRED_BRIEF_FIELDS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "missing_player_goal",
        ("player_goal", "goal", "objective"),
        "Describe what the player is trying to achieve.",
    ),
    (
        "missing_core_loop",
        ("core_loop", "gameplay_loop"),
        "Describe the repeatable actions that form the core gameplay loop.",
    ),
    (
        "missing_controls",
        ("controls", "input", "inputs"),
        "Define the controls or player inputs.",
    ),
    (
        "missing_win_conditions",
        ("win_conditions", "win_condition", "success_condition"),
        "Define how success or meaningful progression is recognized.",
    ),
    (
        "missing_loss_conditions",
        ("loss_conditions", "loss_condition", "failure_condition"),
        "Define failure, loss, or a deliberate no-fail rule.",
    ),
    (
        "missing_restart_behavior",
        ("restart_behavior", "restart", "retry"),
        "Define restart or retry behavior after a terminal state.",
    ),
    (
        "missing_feedback",
        ("feedback", "player_feedback"),
        "Define visible, audible, or textual feedback for important actions and state changes.",
    ),
    (
        "missing_progression",
        ("progression", "difficulty_curve", "challenge_progression"),
        "Define progression or explain why the game intentionally has no progression.",
    ),
)


def _clean_context(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _clean_constraints(values: Iterable[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _clean_context(str(value))
        if normalized and normalized not in seen:
            cleaned.append(normalized)
            seen.add(normalized)
    return tuple(cleaned)


def game_building_requirements(
    *,
    genre: str | None = None,
    runtime: str | None = None,
    extra_constraints: Iterable[str] = (),
) -> tuple[str, ...]:
    """Return deterministic requirements for generating a complete playable game."""

    requirements = list(DEFAULT_GAME_BUILDING_REQUIREMENTS)
    clean_genre = _clean_context(genre)
    clean_runtime = _clean_context(runtime)

    if clean_genre:
        requirements.append(
            f"Genre context: design for {clean_genre} while keeping the core loop explicit and testable."
        )
    if clean_runtime:
        requirements.append(
            f"Runtime context: target {clean_runtime}; preserve its API, performance, input, and packaging constraints."
        )
    requirements.extend(f"Project constraint: {item}" for item in _clean_constraints(extra_constraints))
    return tuple(requirements)


def apply_game_building_skill(
    prompt: str,
    *,
    genre: str | None = None,
    runtime: str | None = None,
    extra_constraints: Iterable[str] = (),
) -> str:
    """Append shared game-building requirements to a generation prompt once.

    The marker check makes composition idempotent when multiple orchestration
    layers apply the skill to the same prompt.
    """

    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")

    base = prompt.strip()
    if GAME_BUILDING_SECTION in base:
        return base

    requirements = game_building_requirements(
        genre=genre,
        runtime=runtime,
        extra_constraints=extra_constraints,
    )
    bullets = "\n".join(f"- {requirement}" for requirement in requirements)
    if base:
        return f"{base}\n\n{GAME_BUILDING_SECTION}\n{bullets}"
    return f"{GAME_BUILDING_SECTION}\n{bullets}"


@dataclass(frozen=True)
class GameBuildIssue:
    """One actionable problem found in a generated game brief."""

    code: str
    field: str
    message: str


def _has_meaningful_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_has_meaningful_value(item) for item in value)
    return True


def validate_game_brief(brief: Mapping[str, object]) -> tuple[GameBuildIssue, ...]:
    """Validate the minimum design information needed before generating code.

    Alias fields are accepted because different generators use different
    vocabulary (for example ``objective`` versus ``player_goal``).
    """

    if not isinstance(brief, Mapping):
        raise TypeError("brief must be a mapping")

    issues: list[GameBuildIssue] = []
    for code, aliases, message in _REQUIRED_BRIEF_FIELDS:
        if not any(_has_meaningful_value(brief.get(alias)) for alias in aliases):
            issues.append(GameBuildIssue(code=code, field=aliases[0], message=message))
    return tuple(issues)


@dataclass(frozen=True)
class GameBuildingSkill:
    """Reusable prompt-and-validation skill for AI game builders."""

    genre: str | None = None
    runtime: str | None = None
    extra_constraints: tuple[str, ...] = ()

    @property
    def requirements(self) -> tuple[str, ...]:
        return game_building_requirements(
            genre=self.genre,
            runtime=self.runtime,
            extra_constraints=self.extra_constraints,
        )

    def apply(self, prompt: str) -> str:
        return apply_game_building_skill(
            prompt,
            genre=self.genre,
            runtime=self.runtime,
            extra_constraints=self.extra_constraints,
        )

    def validate(self, brief: Mapping[str, object]) -> tuple[GameBuildIssue, ...]:
        return validate_game_brief(brief)


__all__ = [
    "DEFAULT_GAME_BUILDING_REQUIREMENTS",
    "GAME_BUILDING_SECTION",
    "GameBuildIssue",
    "GameBuildingSkill",
    "apply_game_building_skill",
    "game_building_requirements",
    "validate_game_brief",
]
