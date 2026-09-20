"""CLI for machine repository manifests, analysis and steward views."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .budgets import derive_zone_budgets
from .builder import RepositoryModelBuilder
from .context import context_for_intent
from .governance import validate_governance
from .growth import growth_recommendations
from .health import repository_health
from .hotspots import structural_hotspots
from .manifest import save_manifest
from .planner import candidate_payload
from .reorganize import propose_reorganization
from .retrieval import RepositoryRetrievalIndex
from .shards import shard_index
from .steward import select_steward_plan
from .workspace import generate_workspace


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
    parser.add_argument("--hotspots", action="store_true")
    parser.add_argument("--governance", action="store_true")
    parser.add_argument("--reorganize", action="store_true")
    parser.add_argument("--budgets", action="store_true")
    parser.add_argument("--search", default="")
    parser.add_argument("--workspace", default="")
    parser.add_argument(
        "--intent",
        choices=[
            "overview", "repair", "architecture", "testing",
            "security", "documentation", "performance",
        ],
        default="",
    )
    args = parser.parse_args()

    builder = RepositoryModelBuilder(args.root)
    model = builder.build()

    if args.workspace:
        files = generate_workspace(
            model,
            builder.config,
            args.workspace,
        )
        payload: object = {
            "repository_fingerprint": model.fingerprint,
            "workspace": args.workspace,
            "files": list(files),
        }
    elif args.search:
        payload = {
            "repository_fingerprint": model.fingerprint,
            "query": args.search,
            "hits": [
                item.as_dict()
                for item in RepositoryRetrievalIndex(model).search(args.search)
            ],
        }
    elif args.hotspots:
        payload = {
            "repository_fingerprint": model.fingerprint,
            "hotspots": [
                item.as_dict()
                for item in structural_hotspots(model)
            ],
        }
    elif args.governance:
        payload = {
            "repository_fingerprint": model.fingerprint,
            "violations": [
                item.as_dict()
                for item in validate_governance(model, builder.config)
            ],
        }
    elif args.reorganize:
        payload = {
            "repository_fingerprint": model.fingerprint,
            "proposals": [
                item.as_dict()
                for item in propose_reorganization(model, builder.config)
            ],
        }
    elif args.budgets:
        payload = {
            "repository_fingerprint": model.fingerprint,
            "zones": [
                item.as_dict()
                for item in derive_zone_budgets(model)
            ],
        }
    elif args.health:
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
        args.steward, args.shards, args.hotspots, args.governance,
        args.reorganize, args.budgets, bool(args.search),
        bool(args.workspace), bool(args.intent),
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
