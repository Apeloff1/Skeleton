"""Import-free audit of CommandSpec mutating versus auth_required.

Mutating commands must require a seal. Inspection commands may be public.
``memory`` is the sealed read. This snapshot reports that invariant without
executing handlers.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import command_contract_specs
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


AUTHZ_AUDIT_KIND: Final = "authz_audit"


def authz_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable mutating/auth_required invariant audit."""

    rows: list[dict[str, object]] = []
    mutating_without_auth: list[str] = []
    auth_without_mutating: list[str] = []
    for spec in command_contract_specs():
        name = str(spec["command"])
        mutating = bool(spec["mutating"])
        auth_required = bool(spec["auth_required"])
        if mutating and not auth_required:
            mutating_without_auth.append(name)
        if auth_required and not mutating:
            auth_without_mutating.append(name)
        rows.append(
            {
                "command": name,
                "mutating": mutating,
                "auth_required": auth_required,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": AUTHZ_AUDIT_KIND,
        "commands": rows,
        "mutating_without_auth": mutating_without_auth,
        "auth_without_mutating": auth_without_mutating,
    }


def get_authz_audit_row(command_id: str) -> dict[str, object]:
    """Return one authz-audit row by command name."""

    if not isinstance(command_id, str):
        raise TypeError("command_id must be a string")
    normalized = command_id.strip().lower()
    if not normalized:
        raise ValueError("command_id must not be empty")
    for row in authz_audit_snapshot()["commands"]:
        if row["command"] == normalized:
            return dict(row)
    raise KeyError(f"unknown command: {normalized}")
