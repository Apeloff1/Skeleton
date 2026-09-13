"""Shared fail-closed guard for user-controlled code execution.

User supplied programs are arbitrary code. They must never become executable
because a deployment inherited a single permissive environment variable. The
guard therefore requires an explicit opt-in and, in production-like runtimes,
a second acknowledgement of the risk.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_PRODUCTION_MARKERS = (
    "EMERGENT_DEPLOY",
    "K_SERVICE",
    "KUBERNETES_SERVICE_HOST",
    "DYNO",
    "WEBSITE_INSTANCE_ID",
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def production_runtime(environ: Mapping[str, str] | None = None) -> bool:
    """Return True when common deployment markers indicate a hosted runtime."""
    env = os.environ if environ is None else environ
    if _truthy(env.get("EMERGENT_DEPLOY")):
        return True
    return any(bool((env.get(name) or "").strip()) for name in _PRODUCTION_MARKERS[1:])


@dataclass(frozen=True)
class ExecutionPolicy:
    enabled: bool
    production: bool
    reason: str


def execution_policy(environ: Mapping[str, str] | None = None) -> ExecutionPolicy:
    """Resolve the effective arbitrary-code execution policy.

    Development requires ``ALLOW_UNSAFE_CODE_EXECUTION=true``. Production-like
    environments additionally require ``ACKNOWLEDGE_PRODUCTION_RCE_RISK=true``.
    The two-key production gate makes accidental exposure fail closed.
    """
    env = os.environ if environ is None else environ
    opted_in = _truthy(env.get("ALLOW_UNSAFE_CODE_EXECUTION"))
    production = production_runtime(env)

    if not opted_in:
        return ExecutionPolicy(False, production, "unsafe execution was not explicitly enabled")

    if production and not _truthy(env.get("ACKNOWLEDGE_PRODUCTION_RCE_RISK")):
        return ExecutionPolicy(
            False,
            True,
            "production execution requires an explicit second risk acknowledgement",
        )

    return ExecutionPolicy(True, production, "explicitly enabled")


def code_execution_enabled() -> bool:
    """Return whether user-controlled code execution is explicitly allowed."""
    return execution_policy().enabled


def execution_disabled_message(action: str = "Code execution") -> str:
    policy = execution_policy()
    suffix = (
        " In production, ACKNOWLEDGE_PRODUCTION_RCE_RISK=true is also required."
        if policy.production
        else ""
    )
    return (
        f"{action} is disabled by default ({policy.reason}). "
        "Set ALLOW_UNSAFE_CODE_EXECUTION=true only inside a trusted sandbox."
        f"{suffix}"
    )


def execution_disabled_response(action: str = "Code execution") -> dict:
    policy = execution_policy()
    return {
        "ok": False,
        "disabled": True,
        "production": policy.production,
        "error": execution_disabled_message(action),
    }


def require_execution_allowed(action: str = "Code execution") -> bool:
    """Compatibility helper used by execution call sites."""
    del action
    return code_execution_enabled()
