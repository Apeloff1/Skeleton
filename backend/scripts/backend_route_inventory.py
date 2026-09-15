"""Static inventory for the registered FastAPI route surface.

The scanner intentionally does not import route modules. It reads the canonical
``core/routes_registry.py`` declarations and parses route modules with ``ast``
so CI can inventory the API without booting databases, model stacks, provider
SDKs, or optional integrations.

Supported static composition includes:
* module-level ``APIRouter(prefix=...)`` declarations;
* registered root routers that ``include_router`` child routers;
* decorators on module-scope route functions;
* literal ``add_api_route`` registrations;
* router-factory functions such as ``_make_router(router, kind)`` whose route
  decorators target a router parameter and are invoked at module scope with a
  statically named child router.

Anything outside that intentionally bounded model is emitted as unresolved
evidence rather than guessed. This makes the output suitable for staged,
fail-closed route-policy rollout.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections.abc import Iterable
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


@dataclass(frozen=True, slots=True)
class RouterDecl:
    name: str
    prefix: str
    source_line: int


@dataclass(frozen=True, slots=True)
class IncludeEdge:
    parent: str
    child: str
    prefix: str
    source_line: int


@dataclass(frozen=True, slots=True)
class RouteTemplate:
    router_name: str
    method: str
    path: str
    source_line: int


@dataclass(frozen=True, slots=True)
class FactoryRouteTemplate:
    router_parameter: str
    method: str
    path: str
    source_line: int


class StaticStringResolver:
    """Resolve a deliberately small deterministic subset of string ASTs."""

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


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _module_scope_statements(statements: Iterable[ast.stmt]) -> Iterable[ast.stmt]:
    """Yield module-scope statements, descending control flow but never functions/classes."""

    for node in statements:
        yield node
        if isinstance(node, ast.If):
            yield from _module_scope_statements(node.body)
            yield from _module_scope_statements(node.orelse)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            yield from _module_scope_statements(node.body)
            yield from _module_scope_statements(node.orelse)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            yield from _module_scope_statements(node.body)
        elif isinstance(node, ast.Try):
            yield from _module_scope_statements(node.body)
            for handler in node.handlers:
                yield from _module_scope_statements(handler.body)
            yield from _module_scope_statements(node.orelse)
            yield from _module_scope_statements(node.finalbody)
        elif isinstance(node, ast.Match):
            for case in node.cases:
                yield from _module_scope_statements(case.body)


def _router_declarations(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> tuple[dict[str, RouterDecl], list[UnresolvedRecord]]:
    routers: dict[str, RouterDecl] = {}
    unresolved: list[UnresolvedRecord] = []
    for node in _module_scope_statements(tree.body):
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            continue
        if _call_name(value.func) != "APIRouter":
            continue
        prefix_node = next((keyword.value for keyword in value.keywords if keyword.arg == "prefix"), None)
        prefix = "" if prefix_node is None else resolver.resolve(prefix_node)
        if prefix is None:
            unresolved.append(
                UnresolvedRecord(
                    module="<pending>",
                    reason=f"router {target.id!r} uses a dynamic prefix",
                    source_line=getattr(node, "lineno", None),
                )
            )
            continue
        routers[target.id] = RouterDecl(target.id, prefix, getattr(node, "lineno", 0))
    return routers, unresolved


def _include_edges(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> tuple[list[IncludeEdge], list[tuple[int, str]]]:
    edges: list[IncludeEdge] = []
    dynamic: list[tuple[int, str]] = []
    for node in _module_scope_statements(tree.body):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "include_router":
            continue
        if not isinstance(call.func.value, ast.Name):
            continue
        parent = call.func.value.id
        child_node = call.args[0] if call.args else next(
            (keyword.value for keyword in call.keywords if keyword.arg == "router"),
            None,
        )
        if not isinstance(child_node, ast.Name):
            dynamic.append((getattr(call, "lineno", 0), f"{parent}.include_router uses dynamic child"))
            continue
        prefix_node = next((keyword.value for keyword in call.keywords if keyword.arg == "prefix"), None)
        prefix = "" if prefix_node is None else resolver.resolve(prefix_node)
        if prefix is None:
            dynamic.append((getattr(call, "lineno", 0), f"{parent}.include_router uses dynamic prefix"))
            continue
        edges.append(IncludeEdge(parent, child_node.id, prefix, getattr(call, "lineno", 0)))
    return edges, dynamic


def _reachable_router_prefixes(
    root: RegisteredModule,
    routers: dict[str, RouterDecl],
    edges: list[IncludeEdge],
) -> tuple[dict[str, str], list[UnresolvedRecord]]:
    unresolved: list[UnresolvedRecord] = []
    root_decl = routers.get(root.router_attr)
    if root_decl is None:
        return {}, [
            UnresolvedRecord(root.module, f"router {root.router_attr!r} is not a static APIRouter declaration")
        ]

    by_parent: dict[str, list[IncludeEdge]] = {}
    for edge in edges:
        by_parent.setdefault(edge.parent, []).append(edge)

    prefixes = {root.router_attr: _normalize_path(root.mount_prefix, root_decl.prefix)}
    queue = [root.router_attr]
    while queue:
        parent = queue.pop(0)
        parent_prefix = prefixes[parent]
        for edge in by_parent.get(parent, []):
            child_decl = routers.get(edge.child)
            if child_decl is None:
                unresolved.append(
                    UnresolvedRecord(
                        root.module,
                        f"included router {edge.child!r} is not a static APIRouter declaration",
                        edge.source_line,
                    )
                )
                continue
            effective = _normalize_path(parent_prefix, edge.prefix, child_decl.prefix)
            previous = prefixes.get(edge.child)
            if previous is not None and previous != effective:
                unresolved.append(
                    UnresolvedRecord(
                        root.module,
                        f"router {edge.child!r} is included at multiple effective prefixes",
                        edge.source_line,
                    )
                )
                continue
            if previous is None:
                prefixes[edge.child] = effective
                queue.append(edge.child)
    return prefixes, unresolved


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


def _route_from_decorator(
    decorator: ast.AST,
    resolver: StaticStringResolver,
) -> tuple[str, tuple[str, ...], str, int] | None:
    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
        return None
    owner = decorator.func.value
    if not isinstance(owner, ast.Name):
        return None
    verb = decorator.func.attr.lower()
    if verb not in _HTTP_METHODS and verb != "api_route":
        return None
    path_node = decorator.args[0] if decorator.args else next(
        (keyword.value for keyword in decorator.keywords if keyword.arg in {"path", "url"}),
        None,
    )
    path = resolver.resolve(path_node)
    if path is None:
        return owner.id, (), "", getattr(decorator, "lineno", 0)
    methods = _methods_from_api_route(decorator, resolver) if verb == "api_route" else (verb.upper(),)
    return owner.id, methods, path, getattr(decorator, "lineno", 0)


def _module_route_templates(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> tuple[list[RouteTemplate], list[tuple[str, int]]]:
    templates: list[RouteTemplate] = []
    dynamic: list[tuple[str, int]] = []
    for node in _module_scope_statements(tree.body):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            parsed = _route_from_decorator(decorator, resolver)
            if parsed is None:
                continue
            owner, methods, path, line = parsed
            if not methods:
                dynamic.append((f"dynamic decorator path on {node.name}", line))
                continue
            templates.extend(RouteTemplate(owner, method, path, line) for method in methods)
    return templates, dynamic


def _factory_route_templates(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> dict[str, tuple[FactoryRouteTemplate, ...]]:
    factories: dict[str, tuple[FactoryRouteTemplate, ...]] = {}
    for factory in tree.body:
        if not isinstance(factory, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parameters = {argument.arg for argument in factory.args.args}
        templates: list[FactoryRouteTemplate] = []
        for node in ast.walk(factory):
            if node is factory or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                parsed = _route_from_decorator(decorator, resolver)
                if parsed is None:
                    continue
                owner, methods, path, line = parsed
                if owner not in parameters or not methods:
                    continue
                templates.extend(
                    FactoryRouteTemplate(owner, method, path, line) for method in methods
                )
        if templates:
            factories[factory.name] = tuple(templates)
    return factories


def _factory_bindings(
    tree: ast.Module,
    factories: dict[str, tuple[FactoryRouteTemplate, ...]],
) -> list[tuple[str, ast.Call]]:
    calls: list[tuple[str, ast.Call]] = []
    for node in _module_scope_statements(tree.body):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        name = _call_name(node.value.func)
        if name in factories:
            calls.append((name, node.value))
    return calls


def _factory_parameter_router(
    tree: ast.Module,
    factory_name: str,
    parameter: str,
    call: ast.Call,
) -> str | None:
    factory = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == factory_name
        ),
        None,
    )
    if factory is None:
        return None
    parameter_names = [argument.arg for argument in factory.args.args]
    try:
        index = parameter_names.index(parameter)
    except ValueError:
        return None
    value: ast.AST | None = call.args[index] if index < len(call.args) else None
    if value is None:
        value = next((keyword.value for keyword in call.keywords if keyword.arg == parameter), None)
    return value.id if isinstance(value, ast.Name) else None


def _imperative_templates(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> tuple[list[RouteTemplate], list[tuple[str, int]]]:
    templates: list[RouteTemplate] = []
    dynamic: list[tuple[str, int]] = []
    for node in _module_scope_statements(tree.body):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "add_api_route":
            continue
        if not isinstance(call.func.value, ast.Name):
            continue
        owner = call.func.value.id
        path_node = call.args[0] if call.args else next(
            (keyword.value for keyword in call.keywords if keyword.arg == "path"),
            None,
        )
        path = resolver.resolve(path_node)
        if path is None:
            dynamic.append(("dynamic add_api_route path", getattr(call, "lineno", 0)))
            continue
        for method in _methods_from_api_route(call, resolver):
            templates.append(RouteTemplate(owner, method, path, getattr(call, "lineno", 0)))
    return templates, dynamic


def _scan_module(
    tree: ast.Module,
    module: RegisteredModule,
    resolver: StaticStringResolver,
) -> tuple[list[RouteRecord], list[UnresolvedRecord]]:
    routers, router_unresolved = _router_declarations(tree, resolver)
    unresolved = [
        UnresolvedRecord(module.module, row.reason, row.source_line) for row in router_unresolved
    ]
    edges, dynamic_edges = _include_edges(tree, resolver)
    unresolved.extend(
        UnresolvedRecord(module.module, reason, line) for line, reason in dynamic_edges
    )
    effective, reachability_unresolved = _reachable_router_prefixes(module, routers, edges)
    unresolved.extend(reachability_unresolved)
    if not effective:
        return [], unresolved

    routes: list[RouteRecord] = []
    templates, dynamic_routes = _module_route_templates(tree, resolver)
    imperative, dynamic_imperative = _imperative_templates(tree, resolver)
    templates.extend(imperative)
    unresolved.extend(
        UnresolvedRecord(module.module, reason, line)
        for reason, line in (*dynamic_routes, *dynamic_imperative)
    )

    for template in templates:
        prefix = effective.get(template.router_name)
        if prefix is None:
            continue
        routes.append(
            RouteRecord(
                module=module.module,
                router_attr=template.router_name,
                method=template.method,
                path=_normalize_path(prefix, template.path),
                source_line=template.source_line,
            )
        )

    factories = _factory_route_templates(tree, resolver)
    for factory_name, call in _factory_bindings(tree, factories):
        for template in factories[factory_name]:
            router_name = _factory_parameter_router(
                tree, factory_name, template.router_parameter, call
            )
            if router_name is None:
                unresolved.append(
                    UnresolvedRecord(
                        module.module,
                        f"factory {factory_name!r} binds router parameter "
                        f"{template.router_parameter!r} dynamically",
                        getattr(call, "lineno", None),
                    )
                )
                continue
            prefix = effective.get(router_name)
            if prefix is None:
                continue
            routes.append(
                RouteRecord(
                    module=module.module,
                    router_attr=router_name,
                    method=template.method,
                    path=_normalize_path(prefix, template.path),
                    source_line=template.source_line,
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
        module_routes, module_unresolved = _scan_module(tree, module, resolver)
        routes.extend(module_routes)
        unresolved.extend(module_unresolved)

    routes.sort(key=lambda row: (row.path, row.method, row.module, row.router_attr, row.source_line))
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
    parser.add_argument(
        "--fail-on-duplicates",
        action="store_true",
        help="exit non-zero when duplicate method+path registrations exist",
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
    failed = (args.strict and not report.complete) or (
        args.fail_on_duplicates and report.duplicate_route_count > 0
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
