from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
from pathlib import Path
from typing import Any, Sequence

from .plan_store import InMemoryPlanStore
from .runtime import build_supervisor

_STATE_PREFIX = "gz:v1:"


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


def _read_state(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {"version": 1, "plan_items": [], "workers": [], "revisions": []}
    if raw.startswith(_STATE_PREFIX):
        try:
            packed = base64.b64decode(raw[len(_STATE_PREFIX) :], validate=True)
            raw = gzip.decompress(packed).decode("utf-8")
        except (ValueError, OSError) as exc:
            raise ValueError("invalid compressed shift-supervisor state") from exc
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("shift-supervisor state must contain a JSON object")
    return value


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    packed = gzip.compress(raw, compresslevel=9)
    encoded = _STATE_PREFIX + base64.b64encode(packed).decode("ascii")
    path.write_text(encoded + "\n", encoding="utf-8")


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
    parser.add_argument(
        "--state-in",
        help="optional durable state file restored before running",
    )
    parser.add_argument(
        "--state-out",
        help="optional compressed durable state file written after running",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    store = InMemoryPlanStore()
    if args.state_in:
        state_path = Path(args.state_in)
        if state_path.exists():
            store.restore_state(_read_state(state_path))

    scheduler = build_supervisor(project_context_supplier=_context, store=store)
    if not args.once:
        if args.output or args.state_out:
            raise SystemExit("--output/--state-out require --once")
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
    if args.state_out:
        _write_state(Path(args.state_out), store.export_state())
    print(encoded)


if __name__ == "__main__":
    main()
