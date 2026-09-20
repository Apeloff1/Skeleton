"""CLI for deterministic machine repository manifests and steward views."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .builder import build_repository_model
from .context import context_for_intent
from .growth import growth_recommendations
from .health import repository_health
from .manifest import save_manifest
from .planner import candidate_payload
from .shards import shard_index
from .steward import select_steward_plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--work", action="store_true")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--growth", action="store_true")
    parser.add_argument("--steward", action="store_true")
    parser.add_argument("--shards", action="store_true")
    parser.add_argument(
        "--intent",
        choices=[
            "overview", "repair", "architecture", "testing",
            "security", "documentation", "performance",
        ],
        default="",
    )
    args = parser.parse_args()

    model = build_repository_model(args.root)
    if args.health:
        payload = repository_health(model).as_dict()
    elif args.growth:
        payload = {
            "repository_fingerprint": model.fingerprint,
            "recommendations": [
                item.as_dict()
                for item in growth_recommendations(model)
            ],
        }
    elif args.steward:
        payload = select_steward_plan(model).as_dict()
    elif args.shards:
        payload = shard_index(model)
    elif args.intent:
        payload = context_for_intent(model, args.intent)
    elif args.work:
        payload = candidate_payload(model)
    elif args.summary:
        payload = model.machine_context()
    else:
        payload = model.as_dict()

    if args.output and not any((
        args.summary, args.work, args.health, args.growth,
        args.steward, args.shards, bool(args.intent),
    )):
        save_manifest(model, args.output)
        return 0

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
