"""Import-free audit of command contracts versus runtime register.

``CommandSpec`` rows in ``command_contracts`` are the transport-neutral
surface. ``build_runtime_command_service`` must register a handler for each
spec. This snapshot reports that without executing commands or importing
genesis.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import command_contract_specs, runtime_registered_commands
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


CONTRACT_AUDIT_KIND: Final = "contract_audit"


def contract_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable command-contract versus runtime-register audit."""

    specs = command_contract_specs()
    registered = runtime_registered_commands()
    registered_set = set(registered)
    rows: list[dict[str, object]] = []
    for spec in specs:
        name = str(spec["command"])
        rows.append(
            {
                "command": name,
                "in_contract": True,
                "in_runtime": name in registered_set,
                "auth_required": bool(spec["auth_required"]),
                "mutating": bool(spec["mutating"]),
            }
        )
    extras = [name for name in registered if name not in {str(spec["command"]) for spec in specs}]
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": CONTRACT_AUDIT_KIND,
        "commands": rows,
        "missing_from_runtime": [str(spec["command"]) for spec in specs if spec["command"] not in registered_set],
        "missing_from_contract": extras,
    }


def get_contract_audit_row(command_id: str) -> dict[str, object]:
    """Return one contract-audit row by command name."""

    if not isinstance(command_id, str):
        raise TypeError("command_id must be a string")
    normalized = command_id.strip().lower()
    if not normalized:
        raise ValueError("command_id must not be empty")
    for row in contract_audit_snapshot()["commands"]:
        if row["command"] == normalized:
            return dict(row)
    raise KeyError(f"unknown command: {normalized}")
