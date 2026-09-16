from __future__ import annotations

import json
import os

from .runtime import build_supervisor


def _context():
    raw = os.getenv("SHIFT_PROJECT_CONTEXT_JSON", "{}")
    context = json.loads(raw)
    if not isinstance(context, dict):
        raise ValueError("SHIFT_PROJECT_CONTEXT_JSON must contain a JSON object")
    return context


def main() -> None:
    scheduler = build_supervisor(project_context_supplier=_context)
    scheduler.run_forever()


if __name__ == "__main__":
    main()
