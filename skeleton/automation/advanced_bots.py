"""Advanced bot contracts used by the repository bot manager.

These are deterministic planners: the model may suggest work, but policy code
chooses whether a bot is allowed to act. Execution remains in isolated PRs.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class AdvancedBot:
    name: str
    trigger: str
    risk: str
    max_files: int
    requires_tests: bool = True


ADVANCED_BOTS = (
    AdvancedBot("root-cause", "repeated CI failures", "medium", 6),
    AdvancedBot("dependency-guardian", "dependency/security alerts", "medium", 8),
    AdvancedBot("regression-hunter", "new failing tests or flaky jobs", "medium", 6),
    AdvancedBot("architecture-reviewer", "large PR or subsystem drift", "low", 4),
    AdvancedBot("security-auditor", "security/code-scanning signal", "high", 5),
    AdvancedBot("performance-sentinel", "benchmark or timeout regression", "medium", 5),
    AdvancedBot("release-guardian", "release readiness signal", "high", 5),
    AdvancedBot("documentation-guardian", "docs/code drift", "low", 8),
    AdvancedBot("integration-sentinel", "cross-subsystem integration failure", "medium", 6),
    AdvancedBot("pr-reviewer", "opened or updated PR", "low", 0, False),
)


def allowed(bot: AdvancedBot, changed_files: list[str]) -> bool:
    """Reject control-plane and oversized changes before any model proposal runs."""
    if len(changed_files) > bot.max_files:
        return False
    blocked = (".github/", ".git/", ".env", "secrets/", "deploy/")
    return not any(path.startswith(blocked) for path in changed_files)
