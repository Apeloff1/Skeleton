"""Import-free audit of capability-view flags versus CLI aliases and help.

Every new snapshot adds a mutually exclusive ``capabilities`` flag. Runtime
``_CAPABILITY_VIEW_FLAGS``, ``__main__`` aliases, and the module docstring
must stay aligned. This snapshot reports that without executing commands.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import (
    main_cli_capability_alias_flags,
    main_cli_capability_help_flags,
    runtime_capability_view_flags,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


CAPABILITY_VIEW_AUDIT_KIND: Final = "capability_view_audit"


def capability_view_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable capability-view flag inventory."""

    runtime = runtime_capability_view_flags()
    cli = main_cli_capability_alias_flags()
    help_flags = main_cli_capability_help_flags()
    runtime_set = set(runtime)
    cli_set = set(cli)
    help_set = set(help_flags)
    names = list(dict.fromkeys([*runtime, *cli, *help_flags]))
    rows: list[dict[str, object]] = []
    for name in names:
        rows.append(
            {
                "flag": name,
                "in_runtime": name in runtime_set,
                "in_cli": name in cli_set,
                "in_help": name in help_set,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": CAPABILITY_VIEW_AUDIT_KIND,
        "flags": rows,
        "runtime": runtime,
        "cli": cli,
        "help": help_flags,
        "missing_from_runtime": [name for name in names if name not in runtime_set],
        "missing_from_cli": [name for name in names if name not in cli_set],
        "missing_from_help": [name for name in names if name not in help_set],
    }


def get_capability_view_audit_row(flag_id: str) -> dict[str, object]:
    """Return one capability-view flag row by runtime flag name."""

    if not isinstance(flag_id, str):
        raise TypeError("flag_id must be a string")
    normalized = flag_id.strip()
    if not normalized:
        raise ValueError("flag_id must not be empty")
    for row in capability_view_audit_snapshot()["flags"]:
        if row["flag"] == normalized:
            return dict(row)
    raise KeyError(f"unknown flag: {normalized}")
