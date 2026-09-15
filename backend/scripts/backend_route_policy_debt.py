"""Rank routes still classified in the protected ``legacy_api`` migration bucket."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    backend_root = str(Path(__file__).resolve().parents[1])
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

try:
    from scripts.backend_route_inventory import build_inventory
except ModuleNotFoundError:
    from backend_route_inventory import build_inventory

from core.route_policy_catalog import default_route_domain_policy


def _group_prefix(path: str, depth: int) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "/"
    return "/" + "/".join(parts[: max(depth, 1)])


def build_debt_report(
    registry: Path,
    routes_root: Path,
    *,
    depth: int = 2,
) -> dict[str, object]:
    if depth < 1 or depth > 6:
        raise ValueError("depth must be between 1 and 6")
    inventory = build_inventory(registry, routes_root)
    policy = default_route_domain_policy()

    # Unique paths are the policy migration unit. Multiple methods on the same
    # path should not inflate domain-debt counts.
    legacy_paths = sorted(
        {
            route.path
            for route in inventory.routes
            if policy.required_domain(route.path) == "legacy_api"
        }
    )
    groups = Counter(_group_prefix(path, depth) for path in legacy_paths)
    ranked = sorted(groups.items(), key=lambda item: (-item[1], item[0]))
    return {
        "depth": depth,
        "legacy_path_count": len(legacy_paths),
        "group_count": len(ranked),
        "groups": [
            {"prefix": prefix, "paths": count}
            for prefix, count in ranked
        ],
        "sample_paths": legacy_paths[:50],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("backend/core/routes_registry.py"))
    parser.add_argument("--routes-root", type=Path, default=Path("backend/routes"))
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.top < 1:
        parser.error("--top must be positive")

    try:
        report = build_debt_report(args.registry, args.routes_root, depth=args.depth)
    except ValueError as exc:
        parser.error(str(exc))

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print(
        "route policy legacy debt: "
        f"paths={report['legacy_path_count']} groups={report['group_count']} depth={report['depth']}"
    )
    for row in report["groups"][: args.top]:
        print(f"LEGACY {row['paths']:4d} {row['prefix']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
