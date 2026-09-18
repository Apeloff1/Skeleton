"""Import-free audit of developer CLI commands versus architecture.CLI_COMMANDS.

The help surface documents list-templates/validate/docs in ``cli.py`` while
persistence snapshot commands live only on ``DevCommandRegistry``. This snapshot
reports that split without importing the developer package or rewriting either
registry.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import (
    architecture_cli_commands,
    developer_cli_dispatch_commands,
    developer_registry_commands,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


DEVELOPER_CLI_AUDIT_KIND: Final = "developer_cli_audit"


def developer_cli_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable developer CLI documentation audit."""

    documented = architecture_cli_commands()
    documented_names = [str(row["command"]) for row in documented]
    registry = developer_registry_commands()
    dispatch = developer_cli_dispatch_commands()
    runtime = list(dict.fromkeys([*registry, *dispatch]))
    extras = [name for name in runtime if name not in documented_names]
    names = documented_names + extras
    rows: list[dict[str, object]] = []
    documented_map = {str(row["command"]): row for row in documented}
    for name in names:
        architecture = documented_map.get(name)
        in_registry = name in registry
        in_dispatch = name in dispatch
        rows.append(
            {
                "command": name,
                "architecture_documented": architecture is not None,
                "in_registry": in_registry,
                "in_cli_dispatch": in_dispatch,
                "runtime_present": in_registry or in_dispatch,
                "args": str(architecture["args"]) if architecture else "",
                "description": str(architecture["description"]) if architecture else "",
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": DEVELOPER_CLI_AUDIT_KIND,
        "commands": rows,
        "missing_from_architecture": extras,
        "missing_from_runtime": [name for name in documented_names if name not in set(runtime)],
    }


def get_developer_cli_audit_row(command_id: str) -> dict[str, object]:
    """Return one developer-CLI audit row by command name."""

    if not isinstance(command_id, str):
        raise TypeError("command_id must be a string")
    normalized = command_id.strip().lower()
    if not normalized:
        raise ValueError("command_id must not be empty")
    for row in developer_cli_audit_snapshot()["commands"]:
        if row["command"] == normalized:
            return dict(row)
    raise KeyError(f"unknown command: {normalized}")
