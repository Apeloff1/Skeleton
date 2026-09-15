"""Repository-aware entrypoint for the recursive backend route inventory.

The core AST engine intentionally refuses runtime-computed router children. This
entrypoint supplies the one audited dynamic composition manifest currently used
by Skeleton: ``routes.gameforge_cns`` loads a fixed set of in-repo
``gameforge.api`` routers through ``__import__``. The manifest below mirrors
that fixed runtime list so CI can inventory the actual surface without importing
providers or booting the application.
"""

from __future__ import annotations

import ast
from pathlib import Path

try:  # imported as ``scripts.backend_route_inventory`` from backend tests
    from scripts import backend_route_inventory_core as _core
    from scripts.backend_route_inventory_core import (
        InventoryReport,
        RegisteredModule,
        RouteRecord,
        UnresolvedRecord,
        load_registered_modules,
        module_file,
    )
except ModuleNotFoundError:  # executed directly from ``backend/`` in CI
    import backend_route_inventory_core as _core
    from backend_route_inventory_core import (
        InventoryReport,
        RegisteredModule,
        RouteRecord,
        UnresolvedRecord,
        load_registered_modules,
        module_file,
    )

_CNS_PARENT = "routes.gameforge_cns"
_CNS_MOUNT_PREFIX = "/api/gameforge"
_CNS_STATIC_SUBROUTERS = (
    "gameforge.api.diaries",
    "gameforge.api.scim",
    "gameforge.api.personal_logs",
    "gameforge.api.calendar_api",
    "gameforge.api.neuro_api",
    "gameforge.api.decade_logs_api",
    "gameforge.api.coherence_api",
    "gameforge.api.math_api",
    "gameforge.api.exocortex_api",
    "gameforge.api.security_api",
)


def _backend_module_file(backend_root: Path, module_name: str) -> Path:
    return backend_root / (module_name.replace(".", "/") + ".py")


def _scan_backend_module(
    backend_root: Path,
    module_name: str,
    *,
    router_attr: str = "router",
    mount_prefix: str = "",
    stack: tuple[tuple[str, str], ...] = (),
) -> tuple[list[RouteRecord], list[UnresolvedRecord]]:
    identity = (module_name, router_attr)
    if identity in stack:
        chain = " -> ".join(f"{module}:{attr}" for module, attr in (*stack, identity))
        return [], [UnresolvedRecord(module_name, f"router include cycle: {chain}")]

    path = _backend_module_file(backend_root, module_name)
    if not path.is_file():
        return [], [UnresolvedRecord(module_name, f"module file missing: {path}")]
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [], [
            UnresolvedRecord(module_name, f"module parse failed: {type(exc).__name__}: {exc}")
        ]

    root = RegisteredModule(module_name, router_attr, mount_prefix)
    routes, unresolved, children = _core._scan_source(tree, root)
    next_stack = (*stack, identity)
    for imported, child_mount in children:
        child_routes, child_unresolved = _scan_backend_module(
            backend_root,
            imported.module,
            router_attr=imported.router_attr,
            mount_prefix=child_mount,
            stack=next_stack,
        )
        routes.extend(child_routes)
        unresolved.extend(child_unresolved)
    return routes, unresolved


def _is_cns_dynamic_marker(row: UnresolvedRecord) -> bool:
    return row.module == _CNS_PARENT and "include_router uses dynamic child" in row.reason


def build_inventory(registry_path: Path, routes_root: Path) -> InventoryReport:
    base = _core.build_inventory(registry_path, routes_root)
    routes = list(base.routes)
    unresolved = [row for row in base.unresolved if not _is_cns_dynamic_marker(row)]

    backend_root = routes_root.parent
    for module_name in _CNS_STATIC_SUBROUTERS:
        child_routes, child_unresolved = _scan_backend_module(
            backend_root,
            module_name,
            mount_prefix=_CNS_MOUNT_PREFIX,
        )
        routes.extend(child_routes)
        unresolved.extend(child_unresolved)

    routes.sort(key=lambda row: (row.path, row.method, row.module, row.router_attr, row.source_line))
    unresolved.sort(key=lambda row: (row.module, row.source_line or 0, row.reason))
    keys = [(row.method, row.path) for row in routes]
    return InventoryReport(
        modules_declared=base.modules_declared,
        modules_scanned=base.modules_scanned,
        route_count=len(routes),
        unique_path_count=len({row.path for row in routes}),
        duplicate_route_count=len(keys) - len(set(keys)),
        unresolved_count=len(unresolved),
        routes=tuple(routes),
        unresolved=tuple(unresolved),
    )


def main(argv: list[str] | None = None) -> int:
    parser = _core._parser()
    args = parser.parse_args(argv)
    report = build_inventory(args.registry, args.routes_root)
    if args.json:
        import json

        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(
            "backend route inventory: "
            f"modules={report.modules_scanned}/{report.modules_declared} "
            f"routes={report.route_count} unique_paths={report.unique_path_count} "
            f"duplicates={report.duplicate_route_count} unresolved={report.unresolved_count}"
        )
        for row in report.unresolved[:20]:
            location = f":{row.source_line}" if row.source_line else ""
            print(f"UNRESOLVED {row.module}{location}: {row.reason}")
        if report.unresolved_count > 20:
            print(f"... {report.unresolved_count - 20} additional unresolved record(s)")
    failed = (args.strict and not report.complete) or (
        args.fail_on_duplicates and report.duplicate_route_count > 0
    )
    return 1 if failed else 0


__all__ = [
    "InventoryReport",
    "RegisteredModule",
    "RouteRecord",
    "UnresolvedRecord",
    "build_inventory",
    "load_registered_modules",
    "main",
    "module_file",
]


if __name__ == "__main__":
    raise SystemExit(main())
