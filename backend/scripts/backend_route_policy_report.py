"""Measure canonical route-domain policy against the static backend inventory."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

try:
    from scripts.backend_route_inventory import build_inventory
except ModuleNotFoundError:
    from backend_route_inventory import build_inventory

from core.route_policy_catalog import (
    ROUTE_POLICY_CATALOG_VERSION,
    default_route_domain_policy,
)
from core.route_policy_coverage import build_route_policy_coverage


def build_policy_report(registry: Path, routes_root: Path) -> dict[str, object]:
    inventory = build_inventory(registry, routes_root)
    policy = default_route_domain_policy()
    paths = [row.path for row in inventory.routes]
    coverage = build_route_policy_coverage(policy, paths)

    method_counts = Counter(row.method for row in inventory.routes)
    protected_domain_counts = Counter(domain for _, domain in coverage.protected_paths)
    legacy_count = protected_domain_counts.get("legacy_api", 0)
    protected_count = coverage.protected_routes
    legacy_ratio = legacy_count / protected_count if protected_count else 0.0

    return {
        "policy_version": ROUTE_POLICY_CATALOG_VERSION,
        "inventory": {
            "modules_declared": inventory.modules_declared,
            "modules_scanned": inventory.modules_scanned,
            "route_registrations": inventory.route_count,
            "unique_paths": inventory.unique_path_count,
            "duplicates": inventory.duplicate_route_count,
            "unresolved": inventory.unresolved_count,
            "complete": inventory.complete,
            "method_counts": dict(sorted(method_counts.items())),
        },
        "coverage": coverage.as_dict(),
        "domain_counts": dict(sorted(protected_domain_counts.items())),
        "legacy_api_paths": legacy_count,
        "legacy_api_ratio": legacy_ratio,
        "enforcement_ready": (
            inventory.complete
            and inventory.duplicate_route_count == 0
            and coverage.complete
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("backend/core/routes_registry.py"))
    parser.add_argument("--routes-root", type=Path, default=Path("backend/routes"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-inventory-clean", action="store_true")
    parser.add_argument(
        "--max-legacy-ratio",
        type=float,
        default=None,
        help="optional upper bound for paths still classified into legacy_api",
    )
    args = parser.parse_args(argv)
    if args.max_legacy_ratio is not None and not 0 <= args.max_legacy_ratio <= 1:
        parser.error("--max-legacy-ratio must be between 0 and 1")

    report = build_policy_report(args.registry, args.routes_root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        inventory = report["inventory"]
        coverage = report["coverage"]
        print(
            "route policy report: "
            f"policy={report['policy_version']} "
            f"routes={inventory['route_registrations']} "
            f"unique_paths={inventory['unique_paths']} "
            f"unresolved={inventory['unresolved']} "
            f"duplicates={inventory['duplicates']} "
            f"written={coverage['complete']} "
            f"legacy={report['legacy_api_paths']} "
            f"legacy_ratio={report['legacy_api_ratio']:.4f} "
            f"enforcement_ready={report['enforcement_ready']}"
        )
        print(f"route policy domains: {report['domain_counts']}")

    failed = False
    if args.require_inventory_clean and not report["enforcement_ready"]:
        failed = True
    if (
        args.max_legacy_ratio is not None
        and float(report["legacy_api_ratio"]) > args.max_legacy_ratio
    ):
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
