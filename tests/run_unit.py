#!/usr/bin/env python3
"""Runner used by CI when pytest is not installed."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.test_context as c  # noqa: E402
import tests.test_forge as f  # noqa: E402
import tests.test_jeeves as j  # noqa: E402


def main() -> int:
    fails = 0
    passes = 0
    for mod in (f, j, c):
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if not name.startswith("Test"):
                continue
            inst = cls()
            for mname, meth in inspect.getmembers(inst, inspect.ismethod):
                if not mname.startswith("test_"):
                    continue
                try:
                    meth()
                    print("PASS", name, mname)
                    passes += 1
                except Exception as exc:
                    fails += 1
                    print("FAIL", name, mname, type(exc).__name__, exc)
    print(f"RESULT {passes} ok {fails} fail")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
