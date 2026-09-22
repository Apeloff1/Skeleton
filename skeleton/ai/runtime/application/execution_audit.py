"""Deterministic command execution capability audit.

This module follows the existing audit pattern: no runtime execution,
no mutation, and no persistent state. It reports contract/runtime wiring
from supplied command specifications and handlers.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
KIND = "execution_audit"


def _row(spec: Any, handler_present: bool) -> dict[str, Any]:
    return {
        "command": str(getattr(spec, "name", "")),
        "contracted": True,
        "handler_registered": bool(handler_present),
        "mutating": bool(getattr(spec, "mutating", False)),
        "auth_required": bool(getattr(spec, "auth_required", False)),
        "implementation": str(getattr(spec, "implementation", "shared")),
    }


def execution_audit_snapshot(
    specs: Iterable[Any],
    handlers: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a stable execution wiring snapshot."""

    rows = [_row(spec, getattr(spec, "name", "") in handlers) for spec in specs]
    missing_handlers = [row["command"] for row in rows if not row["handler_registered"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "commands": rows,
        "missing_handlers": missing_handlers,
        "healthy": not missing_handlers,
    }


def get_execution_audit_row(
    command_id: str,
    specs: Iterable[Any],
    handlers: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one execution audit row by command name."""

    for spec in specs:
        if getattr(spec, "name", None) == command_id:
            return _row(spec, command_id in handlers)
    raise KeyError(f"unknown command: {command_id}")
