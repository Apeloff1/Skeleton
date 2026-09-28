#!/usr/bin/env python3
"""Local/CI entry point for the canonical Skeleton cache contract."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.build.cache_contract import cli_main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(cli_main())
