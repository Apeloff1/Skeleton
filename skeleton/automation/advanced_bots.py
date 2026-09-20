"""Deterministic policy registry for specialized repository bots."""
from __future__ import annotations

from dataclasses import dataclass

from .supervisor_runtime import SupervisorRuntimeError, validate_worker_name

_RISKS = frozenset({"low", "medium", "high"})
_MAX_TRIGGER_BYTES = 256
_MAX_FILES = 48


@dataclass(frozen=True)
class AdvancedBot:
    name: str
    trigger: str
    risk: str
    max_files: int
    requires_tests: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name.lower() != self.name:
            raise ValueError("invalid specialist name")
        try:
            validate_worker_name(self.name)
        except SupervisorRuntimeError as exc:
            raise ValueError("invalid specialist name") from exc
        if (
            not isinstance(self.trigger, str)
            or not self.trigger.strip()
            or len(self.trigger.encode("utf-8")) > _MAX_TRIGGER_BYTES
            or any(ord(char) < 32 or ord(char) == 127 for char in self.trigger)
        ):
            raise ValueError("invalid specialist trigger")
        if self.risk not in _RISKS:
            raise ValueError("invalid specialist risk")
        if (
            isinstance(self.max_files, bool)
            or not isinstance(self.max_files, int)
            or self.max_files < 0
            or self.max_files > _MAX_FILES
        ):
            raise ValueError("invalid specialist file budget")
        if not isinstance(self.requires_tests, bool):
            raise ValueError("invalid specialist test policy")


ADVANCED_BOTS = (
    AdvancedBot("root-cause", "repeated CI failures", "medium", 6),
    AdvancedBot("dependency-guardian", "dependency/security alerts", "high", 8),
    AdvancedBot("regression-hunter", "new failing tests or flaky jobs", "medium", 6),
    AdvancedBot(
        "feature-builder",
        "maintainer-approved feature or implementation work",
        "medium",
        36,
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
    "core/activation_security.py",
    "core/shift_supervisor/",
    "backend/security/",
    "backend/scripts/",
    "backend/tests/test_bot_activation_security.py",
    "backend/tests/test_supervisor_workflow_contract.py",
    "backend/tests/test_traffic_manager_workflow_contract.py",
    # Nor may they weaken the canonical merge/unit runners or their own custody
    # regression suite. These exact file paths are represented as prefixes so
    # the shared path checks remain single-sourced and fail closed.
    "tests/run_unit.py",
    "tests/test_autonomous_supervisor.py",
    "tests/test_supervisor_runtime.py",
    "tests/test_cross_subsystem_integration.py",
)
SAFE_PREFIXES = ("skeleton/", "tests/", "docs/")
BUILD_SAFE_PREFIXES = (
    "skeleton/",
    "tests/",
    "docs/",
    "backend/",
    "frontend/",
    "core/",
)


def allowed(bot: AdvancedBot, changed_files: list[str]) -> bool:
    """Reject ambiguous, duplicate, privileged, or oversized proposal paths."""
    if not isinstance(bot, AdvancedBot) or not isinstance(changed_files, list):
        return False
    if len(changed_files) > bot.max_files:
        return False
    seen: set[str] = set()
    safe_prefixes = (
        BUILD_SAFE_PREFIXES
        if bot.name == "feature-builder"
        else SAFE_PREFIXES
    )
    for path in changed_files:
        if (
            not isinstance(path, str)
            or "\\" in path
            or "\x00" in path
            or path.startswith("/")
        ):
            return False
        parts = path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            return False
        if path in seen:
            return False
        seen.add(path)
        if path.startswith(BLOCKED_PREFIXES):
            return False
        if not path.startswith(safe_prefixes):
            return False
    return True
