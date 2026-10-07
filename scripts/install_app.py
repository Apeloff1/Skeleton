#!/usr/bin/env python3
"""Repository-local entrypoint for the Skeleton application installer.

This works before the package is installed by adding the checkout root to
sys.path and delegating to the canonical application CLI.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.app.cli import run_app_cli


def main() -> int:
    return run_app_cli(["install", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
