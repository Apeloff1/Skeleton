"""Print exact duplicate FastAPI method/path registrations from static inventory."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

try:  # imported from backend tests/tools
    from scripts.backend_route_inventory import RouteRecord, build_inventory
except ModuleNotFoundError:  # executed directly from ``backend/`` in CI
    from backend_route_inventory import RouteRecord, build_inventory


def collision_groups(routes: tuple[RouteRecord, ...]) -> tuple[tuple[RouteRecord, ...], ...]:
    grouped: dict[tuple[str, str], list[RouteRecord]] = defaultdict(list)
    for route in routes:
        grouped[(route.method, route.path)].append(route)
    collisions = [
        tuple(sorted(rows, key=lambda row: (row.module, row.router_attr, row.source_line)))
        for rows in grouped.values()
        if len(rows) > 1
    ]
    return tuple(sorted(collisions, key=lambda rows: (rows[0].path, rows[0].method)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("backend/core/routes_registry.py"))
    parser.add_argument("--routes-root", type=Path, default=Path("backend/routes"))
    parser.add_argument("--fail", action="store_true", help="exit non-zero when collisions exist")
    args = parser.parse_args(argv)

    report = build_inventory(args.registry, args.routes_root)
    collisions = collision_groups(report.routes)
    print(
        f"backend route collisions: groups={len(collisions)} "
        f"duplicate_registrations={report.duplicate_route_count}"
    )
    for rows in collisions:
        first = rows[0]
        print(f"COLLISION {first.method} {first.path}")
        for row in rows:
            print(f"  {row.module}:{row.source_line} router={row.router_attr}")
    return 1 if args.fail and collisions else 0


if __name__ == "__main__":
    raise SystemExit(main())
