"""CLI for deterministic machine repository manifests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .builder import build_repository_model
from .planner import candidate_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--work", action="store_true")
    args = parser.parse_args()

    model = build_repository_model(args.root)
    if args.work:
        payload = candidate_payload(model)
    elif args.summary:
        payload = model.machine_context()
    else:
        payload = model.as_dict()

    rendered = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
