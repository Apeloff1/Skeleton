"""AI collaboration policy distilled from Tutolage's live-coding system."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class CollaborationRole(str, Enum):
    COPILOT = "copilot"
    DRIVER = "driver"
    NAVIGATOR = "navigator"
    REVIEWER = "reviewer"


@dataclass(frozen=True)
class CollaborationContext:
    role: CollaborationRole = CollaborationRole.COPILOT
    language: str = "python"
    recent_changes: tuple[str, ...] = ()
    session_id: str | None = None


ROLE_BEHAVIORS = {
    CollaborationRole.COPILOT: "complete, suggest next steps, and provide concise inline help",
    CollaborationRole.DRIVER: "implement the learner's intent while preserving their direction",
    CollaborationRole.NAVIGATOR: "guide architecture, catch errors early, and protect the big picture",
    CollaborationRole.REVIEWER: "inspect changes continuously and surface actionable bugs and improvements",
}


def suggestion_window(cursor_line: int, total_lines: int, before: int = 10, after: int = 5) -> tuple[int, int]:
    """Return a bounded local context window for low-latency live assistance."""
    if cursor_line < 0 or total_lines < 0:
        raise ValueError("cursor_line and total_lines must be non-negative")
    if before < 0 or after < 0:
        raise ValueError("window sizes must be non-negative")
    return max(0, cursor_line - before), min(total_lines, cursor_line + after)


def collaboration_prompt(context: CollaborationContext, task: str) -> str:
    behavior = ROLE_BEHAVIORS[context.role]
    changes = ", ".join(context.recent_changes[-3:]) or "none"
    return (
        f"Act as the {context.role.value} in a learning session. "
        f"Your job is to {behavior}. Language: {context.language}. "
        f"Recent changes: {changes}. Task: {task}"
    )
