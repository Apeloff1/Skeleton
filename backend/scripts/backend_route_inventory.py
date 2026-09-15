"""Compatibility entrypoint for the recursive backend route inventory engine."""

from scripts.backend_route_inventory_core import (
    InventoryReport,
    RegisteredModule,
    RouteRecord,
    UnresolvedRecord,
    build_inventory,
    load_registered_modules,
    main,
    module_file,
)

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
