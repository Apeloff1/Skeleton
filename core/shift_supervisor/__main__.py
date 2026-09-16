from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .runtime import build_supervisor


def _context() -> dict:
    context_file = os.getenv("SHIFT_PROJECT_CONTEXT_FILE", "").strip()
    if context_file:
        raw = Path(context_file).read_text(encoding="utf-8")
    else:
        raw = os.getenv("SHIFT_PROJECT_CONTEXT_JSON", "{}")
    context = json.loads(raw)
    if not isinstance(context, dict):
        raise ValueError("shift project context must contain a JSON object")
    return context


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SMB shift supervisor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one bounded supervisor cycle and exit",
    )
    parser.add_argument(
        "--role",
        choices=("secretary", "manager", "both"),
        default="both",
        help="actor(s) to execute in one-shot mode",
    )
    parser.add_argument(
        "--output",
        help="optional JSON file receiving one-shot plan output",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    scheduler = build_supervisor(project_context_supplier=_context)
    if not args.once:
        if args.output:
            raise SystemExit("--output requires --once")
        scheduler.run_forever()
        return

    result = scheduler.run_once(
        run_secretary=args.role in {"secretary", "both"},
        run_manager=args.role in {"manager", "both"},
    )
    encoded = json.dumps(result, sort_keys=True, indent=2, default=str)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
