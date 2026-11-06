#!/usr/bin/env python3
"""Repository-local entrypoint for the Skeleton application installer.

Run the canonical installer from the checkout while keeping explicitly supplied
private password-file paths relative to the operator's original directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from collections.abc import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.app.cli import run_app_cli


def _caller_bound_arguments(arguments: Sequence[str], caller: Path) -> list[str]:
    """Anchor explicit private file operands before changing to checkout root.

    Do not inspect, print or read the password file here. The canonical setup
    layer remains responsible for permissions, symlink custody and parsing.
    """
    result: list[str] = []
    pending_file = False
    for argument in arguments:
        if pending_file:
            if argument.startswith("--"):
                result.append(argument)
                pending_file = False
                continue
            path = Path(argument)
            result.append(str(caller / path) if not path.is_absolute() else argument)
            pending_file = False
            continue
        if argument == "--admin-password-file":
            result.append(argument)
            pending_file = True
        elif argument.startswith("--admin-password-file="):
            key, value = argument.split("=", 1)
            if value:
                path = Path(value)
                value = str(caller / path) if not path.is_absolute() else value
            result.append(key + "=" + value)
        else:
            result.append(argument)
    return result


def main() -> int:
    caller = Path.cwd()
    arguments = _caller_bound_arguments(sys.argv[1:], caller)
    os.chdir(ROOT)
    return run_app_cli(["install", *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
