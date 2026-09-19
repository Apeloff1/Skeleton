"""Deterministic policy registry for specialized repository bots."""
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
    AdvancedBot("dependency-guardian", "dependency/security alerts", "high", 8),
    AdvancedBot("regression-hunter", "new failing tests or flaky jobs", "medium", 6),
    AdvancedBot(
        "feature-builder",
        "maintainer-approved feature or implementation work",
        "medium",
        10,
    ),
    AdvancedBot("architecture-reviewer", "large PR or subsystem drift", "low", 4),
    AdvancedBot("security-auditor", "security/code-scanning signal", "high", 5),
    AdvancedBot("performance-sentinel", "benchmark or timeout regression", "medium", 5),
    AdvancedBot("release-guardian", "release readiness signal", "high", 5),
    AdvancedBot("documentation-guardian", "docs/code drift", "low", 8, False),
    AdvancedBot("integration-sentinel", "cross-subsystem integration failure", "high", 6),
    AdvancedBot("pr-reviewer", "opened or updated PR", "low", 0, False),
    AdvancedBot("test-gap", "coverage gap without behavior change", "medium", 5),
    AdvancedBot("api-contract", "API/schema contract drift", "high", 6),
)

# Specialist workers are intentionally unable to rewrite their own authority,
# workflow permissions, deployment surface, or repository secret boundary.
BLOCKED_PREFIXES = (
    ".github/",
    ".git/",
    ".env",
    "secrets/",
    "deploy/",
    # Autonomous workers cannot rewrite the automation/security authority plane.
    "skeleton/automation/",
    "skeleton/pr_automation/",
    "skeleton/security/",
    "skeleton/build/",
    # Nor may they weaken the canonical merge/unit runners or their own custody
    # regression suite. These exact file paths are represented as prefixes so
    # the shared path checks remain single-sourced and fail closed.
    "tests/run_unit.py",
    "tests/test_autonomous_supervisor.py",
    "tests/test_supervisor_runtime.py",
    "tests/test_cross_subsystem_integration.py",
)
SAFE_PREFIXES = ("skeleton/", "tests/", "docs/")


def allowed(bot: AdvancedBot, changed_files: list[str]) -> bool:
    """Reject control-plane, traversal, and oversized proposals before execution."""
    if len(changed_files) > bot.max_files:
        return False
    for path in changed_files:
        if not isinstance(path, str) or "\\" in path or "\x00" in path or path.startswith("/"):
            return False
        if ".." in path.split("/") or path.startswith(BLOCKED_PREFIXES):
            return False
        if not path.startswith(SAFE_PREFIXES):
            return False
    return True
