#!/usr/bin/env python3
"""Post-push watcher for direct-to-main commits (dry-run unless ``--post``).

Examples::

    python3 scripts/main_guard_watch.py --last 10
    python3 scripts/main_guard_watch.py --since <sha> --format json
    python3 scripts/main_guard_watch.py --update-state --fail-on-new
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skeleton.main_guard.cli import watch_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(watch_main())
