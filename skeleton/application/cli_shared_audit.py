"""Import-free audit of main-CLI shared-command mapping versus CommandSpec.

``python -m skeleton status`` and ``config`` are aliases of the shared
command dispatcher. ``config`` maps to the ``configuration`` spec, not a
``config`` command. This snapshot reports that without executing genesis.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import command_contract_specs, main_cli_shared_command_map
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


CLI_SHARED_AUDIT_KIND: Final = "cli_shared_audit"


def cli_shared_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable main-CLI shared-command mapping audit."""

    mapped = main_cli_shared_command_map()
    specs = {str(item["command"]) for item in command_contract_specs()}
    rows: list[dict[str, object]] = []
    aliases: dict[str, str] = {}
    for item in mapped:
        cli = str(item["cli"])
        spec = str(item["spec"])
        dispatcher = bool(item["dispatcher"])
        in_contract = (not dispatcher) and spec in specs
        if spec and spec != cli:
            aliases[cli] = spec
        rows.append(
            {
                "cli": cli,
                "spec": spec,
                "dispatcher": dispatcher,
                "in_contract": in_contract,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": CLI_SHARED_AUDIT_KIND,
        "commands": rows,
        "aliases": aliases,
        "missing_from_contract": [
            str(row["cli"]) for row in rows if not row["dispatcher"] and not row["in_contract"]
        ],
    }


def get_cli_shared_audit_row(command_id: str) -> dict[str, object]:
    """Return one shared-command mapping row by CLI command name."""

    if not isinstance(command_id, str):
        raise TypeError("command_id must be a string")
    normalized = command_id.strip().lower()
    if not normalized:
        raise ValueError("command_id must not be empty")
    for row in cli_shared_audit_snapshot()["commands"]:
        if row["cli"] == normalized:
            return dict(row)
    raise KeyError(f"unknown command: {normalized}")
