"""Static inventory for the registered FastAPI route surface.

The scanner intentionally does not import route modules. It reads the canonical
``core/routes_registry.py`` declarations, parses each referenced Python module
with ``ast``, resolves literal ``APIRouter(prefix=...)`` declarations, and
collects decorator/add_api_route paths. This keeps the inventory usable in CI
without booting databases, provider SDKs, model stacks, or optional routers.

The output is evidence for staged fail-closed route-policy rollout; unresolved
static expressions remain explicit instead of being guessed.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_HTTP_METHODS = frozenset(
    {"delete", "get", "head", "options", "patch", "post", "put", "trace", "websocket"}
)
_REGISTRY_NAMES = ("KNOWN_ROUTES_WITH_PREFIX", "KNOWN_ROUTES")


@dataclass(frozen=True, slots=True)
class RegisteredModule:
    module: str
    router_attr: str
    mount_prefix: str


@dataclass(frozen=True, slots=True)
class RouteRecord:
    module: str
    router_attr: str
    method: str
    path: str
    source_line: int


@dataclass(frozen=True, slots=True)
class UnresolvedRecord:
    module: str
    reason: str
    source_line: int | None = None


@dataclass(frozen=True, slots=True)
class InventoryReport:
    modules_declared: int
    modules_scanned: int
    route_count: int
    unique_path_count: int
    duplicate_route_count: int
    unresolved_count: int
    routes: tuple[RouteRecord, ...]
    unresolved: tuple[UnresolvedRecord, ...]

    @property
    def complete(self) -> bool:
        return self.unresolved_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "modules_declared": self.modules_declared,
            "modules_scanned": self.modules_scanned,
            "route_count": self.route_count,
            "unique_path_count": self.unique_path_count,
            "duplicate_route_count": self.duplicate_route_count,
            "unresolved_count": self.unresolved_count,
            "complete": self.complete,
            "routes": [asdict(route) for route in self.routes],
            "unresolved": [asdict(row) for row in self.unresolved],
        }


class StaticStringResolver:
    """Resolve a deliberately small, deterministic subset of string ASTs."""

    def __init__(self, tree: ast.Module) -> None:
        self._values: dict[str, str] = {}
        for node in tree.body:
            target: ast.expr | None = None
            value: ast.expr | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            if isinstance(target, ast.Name) and value is not None:
                resolved = self.resolve(value)
                if resolved is not None:
                    self._values[target.id] = resolved

    def resolve(self, node: ast.AST | None) -> str | None:
        if node is None:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self._values.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.resolve(node.left)
            right = self.resolve(node.right)
            if left is not None and right is not None:
                return left + right
        if isinstance(node, ast.JoinedStr):
            pieces: list[str] = []
            for item in node.values:
                if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                    return None
                pieces.append(item.value)
            return "".join(pieces)
        return None


def _literal_registry_entries(tree: ast.Module, name: str) -> list[tuple[str, ...]]:
    value: ast.AST | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = node.value
            break
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                value = node.value
                break
    if value is None:
        raise ValueError(f"registry assignment {name!r} was not found")
    try:
        raw = ast.literal_eval(value)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise ValueError(f"registry assignment {name!r} is not literal") from exc
    if not isinstance(raw, list):
        raise ValueError(f"registry assignment {name!r} must be a list")
    entries: list[tuple[str, ...]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, tuple) or len(entry) not in {2, 3}:
            raise ValueError(f"{name}[{index}] must be a 2- or 3-tuple")
        if not all(isinstance(part, str) for part in entry):
            raise ValueError(f"{name}[{index}] must contain only strings")
        entries.append(entry)
    return entries


def load_registered_modules(registry_path: Path) -> tuple[RegisteredModule, ...]:
    tree = ast.parse(registry_path.read_text(encoding="utf-8"), filename=str(registry_path))
    modules: list[RegisteredModule] = []
    for registry_name in _REGISTRY_NAMES:
        for entry in _literal_registry_entries(tree, registry_name):
            module, router_attr, *prefix = entry
            modules.append(
                RegisteredModule(
                    module=module,
                    router_attr=router_attr,
                    mount_prefix=prefix[0] if prefix else "",
                )
            )
    return tuple(modules)


def _normalize_path(*parts: str) -> str:
    cleaned = [part.strip("/") for part in parts if part and part != "/"]
    return "/" + "/".join(part for part in cleaned if part)


def _router_prefix(
    tree: ast.Module,
    router_attr: str,
    resolver: StaticStringResolver,
) -> tuple[str | None, int | None]:
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if not isinstance(target, ast.Name) or target.id != router_attr:
            continue
        if not isinstance(value, ast.Call):
            return None, getattr(node, "lineno", None)
        function_name = None
        if isinstance(value.func, ast.Name):
            function_name = value.func.id
        elif isinstance(value.func, ast.Attribute):
            function_name = value.func.attr
        if function_name != "APIRouter":
            return None, getattr(node, "lineno", None)
        prefix_node = next((kw.value for kw in value.keywords if kw.arg == "prefix"), None)
        if prefix_node is None:
            return "", getattr(node, "lineno", None)
        return resolver.resolve(prefix_node), getattr(node, "lineno", None)
    return None, None


def _methods_from_api_route(call: ast.Call, resolver: StaticStringResolver) -> tuple[str, ...]:
    methods_node = next((keyword.value for keyword in call.keywords if keyword.arg == "methods"), None)
    if methods_node is None:
        return ("ANY",)
    if not isinstance(methods_node, (ast.List, ast.Tuple, ast.Set)):
        return ("ANY",)
    methods: list[str] = []
    for element in methods_node.elts:
        method = resolver.resolve(element)
        if method is None:
            return ("ANY",)
        methods.append(method.upper())
    return tuple(sorted(set(methods))) or ("ANY",)


def _decorated_routes(
    tree: ast.Module,
    module: RegisteredModule,
    router_prefix: str,
    resolver: StaticStringResolver,
) -> tuple[list[RouteRecord], list[UnresolvedRecord]]:
    routes: list[RouteRecord] = []
    unresolved: list[UnresolvedRecord] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            owner = decorator.func.value
            if not isinstance(owner, ast.Name) or owner.id != module.router_attr:
                continue
            verb = decorator.func.attr.lower()
            if verb not in _HTTP_METHODS and verb != "api_route":
                continue
            path_node = decorator.args[0] if decorator.args else next(
                (keyword.value for keyword in decorator.keywords if keyword.arg in {"path", "url"}),
                None,
            )
            path = resolver.resolve(path_node)
            if path is None:
                unresolved.append(
                    UnresolvedRecord(
                        module=module.module,
                        reason=f"dynamic decorator path on {node.name}",
                        source_line=getattr(decorator, "lineno", None),
                    )
                )
                continue
            methods = (
                _methods_from_api_route(decorator, resolver)
                if verb == "api_route"
                else (verb.upper(),)
            )
            full_path = _normalize_path(module.mount_prefix, router_prefix, path)
            for method in methods:
                routes.append(
                    RouteRecord(
                        module=module.module,
                        router_attr=module.router_attr,
                        method=method,
                        path=full_path,
                        source_line=getattr(decorator, "lineno", 0),
                    )
                )
    return routes, unresolved


def _imperative_routes(
    tree: ast.Module,
    module: RegisteredModule,
    router_prefix: str,
    resolver: StaticStringResolver,
) -> tuple[list[RouteRecord], list[UnresolvedRecord]]:
    routes: list[RouteRecord] = []
    unresolved: list[UnresolvedRecord] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if (
            not isinstance(owner, ast.Name)
            or owner.id != module.router_attr
            or node.func.attr != "add_api_route"
        ):
            continue
        path_node = node.args[0] if node.args else next(
            (keyword.value for keyword in node.keywords if keyword.arg == "path"),
            None,
        )
        path = resolver.resolve(path_node)
        if path is None:
            unresolved.append(
                UnresolvedRecord(
                    module=module.module,
                    reason="dynamic add_api_route path",
                    source_line=getattr(node, "lineno", None),
                )
            )
            continue
        full_path = _normalize_path(module.mount_prefix, router_prefix, path)
        for method in _methods_from_api_route(node, resolver):
            routes.append(
                RouteRecord(
                    module=module.module,
                    router_attr=module.router_attr,
                    method=method,
                    path=full_path,
                    source_line=getattr(node, "lineno", 0),
                )
            )
    return routes, unresolved


def module_file(routes_root: Path, module_name: str) -> Path:
    if not module_name.startswith("routes."):
        raise ValueError(f"unsupported registered module namespace: {module_name}")
    relative = module_name.removeprefix("routes.").replace(".", "/") + ".py"
    return routes_root / relative


def build_inventory(registry_path: Path, routes_root: Path) -> InventoryReport:
    registered = load_registered_modules(registry_path)
    routes: list[RouteRecord] = []
    unresolved: list[UnresolvedRecord] = []
    scanned = 0

    for module in registered:
        path = module_file(routes_root, module.module)
        if not path.is_file():
            unresolved.append(UnresolvedRecord(module.module, f"module file missing: {path}"))
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            unresolved.append(
                UnresolvedRecord(module.module, f"module parse failed: {type(exc).__name__}: {exc}")
            )
            continue
        scanned += 1
        resolver = StaticStringResolver(tree)
        prefix, prefix_line = _router_prefix(tree, module.router_attr, resolver)
        if prefix is None:
            unresolved.append(
                UnresolvedRecord(
                    module.module,
                    f"router {module.router_attr!r} prefix could not be resolved",
                    prefix_line,
                )
            )
            continue
        decorated, decorated_unresolved = _decorated_routes(tree, module, prefix, resolver)
        imperative, imperative_unresolved = _imperative_routes(tree, module, prefix, resolver)
        routes.extend(decorated)
        routes.extend(imperative)
        unresolved.extend(decorated_unresolved)
        unresolved.extend(imperative_unresolved)

    routes.sort(key=lambda row: (row.path, row.method, row.module, row.source_line))
    unresolved.sort(key=lambda row: (row.module, row.source_line or 0, row.reason))
    keys = [(route.method, route.path) for route in routes]
    duplicate_count = len(keys) - len(set(keys))
    unique_paths = len({route.path for route in routes})
    return InventoryReport(
        modules_declared=len(registered),
        modules_scanned=scanned,
        route_count=len(routes),
        unique_path_count=unique_paths,
        duplicate_route_count=duplicate_count,
        unresolved_count=len(unresolved),
        routes=tuple(routes),
        unresolved=tuple(unresolved),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("backend/core/routes_registry.py"),
        help="path to the canonical route registry",
    )
    parser.add_argument(
        "--routes-root",
        type=Path,
        default=Path("backend/routes"),
        help="filesystem root corresponding to the routes package",
    )
    parser.add_argument("--json", action="store_true", help="emit the full JSON inventory")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when any route/module expression is unresolved",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_inventory(args.registry, args.routes_root)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(
            "backend route inventory: "
            f"modules={report.modules_scanned}/{report.modules_declared} "
            f"routes={report.route_count} unique_paths={report.unique_path_count} "
            f"duplicates={report.duplicate_route_count} unresolved={report.unresolved_count}"
        )
        for unresolved in report.unresolved[:20]:
            location = f":{unresolved.source_line}" if unresolved.source_line else ""
            print(f"UNRESOLVED {unresolved.module}{location}: {unresolved.reason}")
        if report.unresolved_count > 20:
            print(f"... {report.unresolved_count - 20} additional unresolved record(s)")
    return 1 if args.strict and not report.complete else 0


if __name__ == "__main__":
    raise SystemExit(main())
