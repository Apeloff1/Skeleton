"""Import-free audit of ``python -m skeleton`` dispatch versus the help surface.

Architecture ``CLI_COMMANDS`` documents the developer CLI, not the package
entrypoint. ``skeleton.__main__.main`` dispatches run/forge/capabilities and
treats ``-h``/``--help`` as aliases of ``help``. This snapshot reports that
split without importing genesis or rewriting the help text.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import main_cli_dispatch_commands, main_cli_help_commands
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


MAIN_CLI_AUDIT_KIND: Final = "main_cli_audit"


def main_cli_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable main-CLI help versus dispatch audit."""

    help_names = main_cli_help_commands()
    dispatch = main_cli_dispatch_commands()
    runtime = list(dispatch["commands"])
    aliases = list(dispatch["aliases"])
    extras = [name for name in runtime if name not in help_names]
    names = list(dict.fromkeys([*help_names, *runtime]))
    rows: list[dict[str, object]] = []
    for name in names:
        in_help = name in help_names
        in_dispatch = name in runtime
        rows.append(
            {
                "command": name,
                "in_help": in_help,
                "in_dispatch": in_dispatch,
                "runtime_present": in_help or in_dispatch,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": MAIN_CLI_AUDIT_KIND,
        "commands": rows,
        "aliases": aliases,
        "missing_from_help": extras,
        "missing_from_dispatch": [name for name in help_names if name not in set(runtime)],
    }


def get_main_cli_audit_row(command_id: str) -> dict[str, object]:
    """Return one main-CLI audit row by command name."""

    if not isinstance(command_id, str):
        raise TypeError("command_id must be a string")
    normalized = command_id.strip().lower()
    if not normalized:
        raise ValueError("command_id must not be empty")
    for row in main_cli_audit_snapshot()["commands"]:
        if row["command"] == normalized:
            return dict(row)
    raise KeyError(f"unknown command: {normalized}")
