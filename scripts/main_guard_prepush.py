#!/usr/bin/env python3
"""Thin wrapper: `python3 scripts/main_guard_prepush.py run --drift` or `... install`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skeleton.main_guard.prepush import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
