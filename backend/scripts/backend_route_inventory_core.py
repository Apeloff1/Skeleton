"""Recursive static FastAPI route inventory engine.

The engine never imports application route modules. It parses the canonical
registry and route source using :mod:`ast`, follows statically imported child
routers, understands local router factories, and keeps dynamic composition as
explicit unresolved evidence.
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
class ImportedRouter:
    alias: str
    module: str
    router_attr: str
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
    """Resolve a deliberately bounded deterministic subset of string ASTs."""

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


def _module_scope(statements: Iterable[ast.stmt]) -> Iterable[ast.stmt]:
    """Descend module control flow without descending functions or classes."""

    for node in statements:
        yield node
        if isinstance(node, ast.If):
            yield from _module_scope(node.body)
            yield from _module_scope(node.orelse)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            yield from _module_scope(node.body)
            yield from _module_scope(node.orelse)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            yield from _module_scope(node.body)
        elif isinstance(node, ast.Try):
            yield from _module_scope(node.body)
            for handler in node.handlers:
                yield from _module_scope(handler.body)
            yield from _module_scope(node.orelse)
            yield from _module_scope(node.finalbody)
        elif isinstance(node, ast.Match):
            for case in node.cases:
                yield from _module_scope(case.body)


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
    except (TypeError, ValueError, SyntaxError) as exc:
        raise ValueError(f"registry assignment {name!r} is not literal") from exc
    if not isinstance(raw, list):
        raise ValueError(f"registry assignment {name!r} must be a list")
    rows: list[tuple[str, ...]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, tuple) or len(entry) not in {2, 3}:
            raise ValueError(f"{name}[{index}] must be a 2- or 3-tuple")
        if not all(isinstance(part, str) for part in entry):
            raise ValueError(f"{name}[{index}] must contain only strings")
        rows.append(entry)
    return rows


def load_registered_modules(registry_path: Path) -> tuple[RegisteredModule, ...]:
    tree = ast.parse(registry_path.read_text(encoding="utf-8"), filename=str(registry_path))
    rows: list[RegisteredModule] = []
    for registry_name in _REGISTRY_NAMES:
        for entry in _literal_registry_entries(tree, registry_name):
            module, router_attr, *mount_prefix = entry
            rows.append(
                RegisteredModule(
                    module=module,
                    router_attr=router_attr,
                    mount_prefix=mount_prefix[0] if mount_prefix else "",
                )
            )
    return tuple(rows)


def _normalize_path(*parts: str) -> str:
    cleaned = [part.strip("/") for part in parts if part and part != "/"]
    return "/" + "/".join(part for part in cleaned if part)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _router_declarations(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> tuple[dict[str, RouterDecl], list[tuple[str, int]]]:
    routers: dict[str, RouterDecl] = {}
    unresolved: list[tuple[str, int]] = []
    for node in _module_scope(tree.body):
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
        prefix_node = next((kw.value for kw in value.keywords if kw.arg == "prefix"), None)
        prefix = "" if prefix_node is None else resolver.resolve(prefix_node)
        line = getattr(node, "lineno", 0)
        if prefix is None:
            unresolved.append((f"router {target.id!r} uses a dynamic prefix", line))
            continue
        routers[target.id] = RouterDecl(target.id, prefix, line)
    return routers, unresolved


def _imported_routers(tree: ast.Module) -> dict[str, ImportedRouter]:
    """Resolve direct route-router imports even when guarded by try/if blocks."""

    imported: dict[str, ImportedRouter] = {}
    for node in _module_scope(tree.body):
        if (
            not isinstance(node, ast.ImportFrom)
            or not node.module
            or not node.module.startswith("routes.")
        ):
            continue
        for alias in node.names:
            if alias.name != "router":
                continue
            local_name = alias.asname or alias.name
            imported[local_name] = ImportedRouter(
                alias=local_name,
                module=node.module,
                router_attr=alias.name,
                source_line=getattr(node, "lineno", 0),
            )
    return imported


def _include_edges(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> tuple[list[IncludeEdge], list[tuple[str, int]]]:
    edges: list[IncludeEdge] = []
    unresolved: list[tuple[str, int]] = []
    for node in _module_scope(tree.body):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "include_router":
            continue
        if not isinstance(call.func.value, ast.Name):
            continue
        parent = call.func.value.id
        child_node = call.args[0] if call.args else next(
            (kw.value for kw in call.keywords if kw.arg == "router"), None
        )
        line = getattr(call, "lineno", 0)
        if not isinstance(child_node, ast.Name):
            unresolved.append((f"{parent}.include_router uses dynamic child", line))
            continue
        prefix_node = next((kw.value for kw in call.keywords if kw.arg == "prefix"), None)
        prefix = "" if prefix_node is None else resolver.resolve(prefix_node)
        if prefix is None:
            unresolved.append((f"{parent}.include_router uses dynamic prefix", line))
            continue
        edges.append(IncludeEdge(parent, child_node.id, prefix, line))
    return edges, unresolved


def _reachable_prefixes(
    root: RegisteredModule,
    routers: dict[str, RouterDecl],
    imported: dict[str, ImportedRouter],
    edges: list[IncludeEdge],
) -> tuple[dict[str, str], list[UnresolvedRecord]]:
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
    unresolved: list[UnresolvedRecord] = []
    while queue:
        parent = queue.pop(0)
        for edge in by_parent.get(parent, []):
            child_decl = routers.get(edge.child)
            if child_decl is None:
                if edge.child not in imported:
                    unresolved.append(
                        UnresolvedRecord(
                            root.module,
                            f"included router {edge.child!r} is not a static or imported APIRouter",
                            edge.source_line,
                        )
                    )
                continue
            effective = _normalize_path(prefixes[parent], edge.prefix, child_decl.prefix)
            previous = prefixes.get(edge.child)
            if previous is not None and previous != effective:
                unresolved.append(
                    UnresolvedRecord(
                        root.module,
                        f"router {edge.child!r} is included at multiple effective prefixes",
                        edge.source_line,
                    )
                )
            elif previous is None:
                prefixes[edge.child] = effective
                queue.append(edge.child)
    return prefixes, unresolved


def _methods(call: ast.Call, resolver: StaticStringResolver) -> tuple[str, ...]:
    value = next((kw.value for kw in call.keywords if kw.arg == "methods"), None)
    if value is None:
        return ("ANY",)
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return ("ANY",)
    methods: list[str] = []
    for element in value.elts:
        resolved = resolver.resolve(element)
        if resolved is None:
            return ("ANY",)
        methods.append(resolved.upper())
    return tuple(sorted(set(methods))) or ("ANY",)


def _decorator_route(
    decorator: ast.AST,
    resolver: StaticStringResolver,
) -> tuple[str, tuple[str, ...], str, int] | None:
    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
        return None
    if not isinstance(decorator.func.value, ast.Name):
        return None
    owner = decorator.func.value.id
    verb = decorator.func.attr.lower()
    if verb not in _HTTP_METHODS and verb != "api_route":
        return None
    path_node = decorator.args[0] if decorator.args else next(
        (kw.value for kw in decorator.keywords if kw.arg in {"path", "url"}), None
    )
    path = resolver.resolve(path_node)
    line = getattr(decorator, "lineno", 0)
    if path is None:
        return owner, (), "", line
    return owner, (_methods(decorator, resolver) if verb == "api_route" else (verb.upper(),)), path, line


def _route_templates(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> tuple[list[RouteTemplate], list[tuple[str, int]]]:
    rows: list[RouteTemplate] = []
    unresolved: list[tuple[str, int]] = []
    for node in _module_scope(tree.body):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            parsed = _decorator_route(decorator, resolver)
            if parsed is None:
                continue
            owner, methods, path, line = parsed
            if not methods:
                unresolved.append((f"dynamic decorator path on {node.name}", line))
                continue
            rows.extend(RouteTemplate(owner, method, path, line) for method in methods)
    return rows, unresolved


def _imperative_templates(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> tuple[list[RouteTemplate], list[tuple[str, int]]]:
    rows: list[RouteTemplate] = []
    unresolved: list[tuple[str, int]] = []
    for node in _module_scope(tree.body):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "add_api_route":
            continue
        if not isinstance(call.func.value, ast.Name):
            continue
        path_node = call.args[0] if call.args else next(
            (kw.value for kw in call.keywords if kw.arg == "path"), None
        )
        path = resolver.resolve(path_node)
        line = getattr(call, "lineno", 0)
        if path is None:
            unresolved.append(("dynamic add_api_route path", line))
            continue
        rows.extend(
            RouteTemplate(call.func.value.id, method, path, line)
            for method in _methods(call, resolver)
        )
    return rows, unresolved


def _factory_templates(
    tree: ast.Module,
    resolver: StaticStringResolver,
) -> dict[str, tuple[FactoryRouteTemplate, ...]]:
    factories: dict[str, tuple[FactoryRouteTemplate, ...]] = {}
    for factory in tree.body:
        if not isinstance(factory, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parameters = {argument.arg for argument in factory.args.args}
        rows: list[FactoryRouteTemplate] = []
        for node in ast.walk(factory):
            if node is factory or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                parsed = _decorator_route(decorator, resolver)
                if parsed is None:
                    continue
                owner, methods, path, line = parsed
                if owner in parameters and methods:
                    rows.extend(FactoryRouteTemplate(owner, method, path, line) for method in methods)
        if rows:
            factories[factory.name] = tuple(rows)
    return factories


def _factory_calls(
    tree: ast.Module,
    factories: dict[str, tuple[FactoryRouteTemplate, ...]],
) -> list[tuple[str, ast.Call]]:
    rows: list[tuple[str, ast.Call]] = []
    for node in _module_scope(tree.body):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        name = _call_name(node.value.func)
        if name in factories:
            rows.append((name, node.value))
    return rows


def _factory_router_binding(
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
    names = [argument.arg for argument in factory.args.args]
    try:
        index = names.index(parameter)
    except ValueError:
        return None
    value: ast.AST | None = call.args[index] if index < len(call.args) else None
    if value is None:
        value = next((kw.value for kw in call.keywords if kw.arg == parameter), None)
    return value.id if isinstance(value, ast.Name) else None


def _scan_source(
    tree: ast.Module,
    root: RegisteredModule,
) -> tuple[list[RouteRecord], list[UnresolvedRecord], list[tuple[ImportedRouter, str]]]:
    resolver = StaticStringResolver(tree)
    routers, router_dynamic = _router_declarations(tree, resolver)
    imported = _imported_routers(tree)
    edges, edge_dynamic = _include_edges(tree, resolver)
    effective, unresolved = _reachable_prefixes(root, routers, imported, edges)
    unresolved.extend(
        UnresolvedRecord(root.module, reason, line)
        for reason, line in (*router_dynamic, *edge_dynamic)
    )
    if not effective:
        return [], unresolved, []

    templates, route_dynamic = _route_templates(tree, resolver)
    imperative, imperative_dynamic = _imperative_templates(tree, resolver)
    templates.extend(imperative)
    unresolved.extend(
        UnresolvedRecord(root.module, reason, line)
        for reason, line in (*route_dynamic, *imperative_dynamic)
    )

    routes: list[RouteRecord] = []
    for template in templates:
        prefix = effective.get(template.router_name)
        if prefix is None:
            continue
        routes.append(
            RouteRecord(
                module=root.module,
                router_attr=template.router_name,
                method=template.method,
                path=_normalize_path(prefix, template.path),
                source_line=template.source_line,
            )
        )

    factories = _factory_templates(tree, resolver)
    for factory_name, call in _factory_calls(tree, factories):
        for template in factories[factory_name]:
            router_name = _factory_router_binding(
                tree, factory_name, template.router_parameter, call
            )
            if router_name is None:
                unresolved.append(
                    UnresolvedRecord(
                        root.module,
                        f"factory {factory_name!r} binds router parameter "
                        f"{template.router_parameter!r} dynamically",
                        getattr(call, "lineno", None),
                    )
                )
                continue
            prefix = effective.get(router_name)
            if prefix is not None:
                routes.append(
                    RouteRecord(
                        module=root.module,
                        router_attr=router_name,
                        method=template.method,
                        path=_normalize_path(prefix, template.path),
                        source_line=template.source_line,
                    )
                )

    children: list[tuple[ImportedRouter, str]] = []
    for edge in edges:
        child = imported.get(edge.child)
        parent_prefix = effective.get(edge.parent)
        if child is not None and parent_prefix is not None:
            children.append((child, _normalize_path(parent_prefix, edge.prefix)))
    return routes, unresolved, children


def module_file(routes_root: Path, module_name: str) -> Path:
    if not module_name.startswith("routes."):
        raise ValueError(f"unsupported registered module namespace: {module_name}")
    relative = module_name.removeprefix("routes.").replace(".", "/") + ".py"
    return routes_root / relative


def _scan_registered(
    root: RegisteredModule,
    routes_root: Path,
    *,
    stack: tuple[tuple[str, str], ...] = (),
) -> tuple[list[RouteRecord], list[UnresolvedRecord]]:
    identity = (root.module, root.router_attr)
    if identity in stack:
        chain = " -> ".join(f"{module}:{attr}" for module, attr in (*stack, identity))
        return [], [UnresolvedRecord(root.module, f"router include cycle: {chain}")]
    path = module_file(routes_root, root.module)
    if not path.is_file():
        return [], [UnresolvedRecord(root.module, f"module file missing: {path}")]
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [], [
            UnresolvedRecord(root.module, f"module parse failed: {type(exc).__name__}: {exc}")
        ]

    routes, unresolved, children = _scan_source(tree, root)
    next_stack = (*stack, identity)
    for imported, mount_prefix in children:
        child_routes, child_unresolved = _scan_registered(
            RegisteredModule(imported.module, imported.router_attr, mount_prefix),
            routes_root,
            stack=next_stack,
        )
        routes.extend(child_routes)
        unresolved.extend(child_unresolved)
    return routes, unresolved


def build_inventory(registry_path: Path, routes_root: Path) -> InventoryReport:
    registered = load_registered_modules(registry_path)
    routes: list[RouteRecord] = []
    unresolved: list[UnresolvedRecord] = []
    scanned = 0
    for root in registered:
        if module_file(routes_root, root.module).is_file():
            scanned += 1
        root_routes, root_unresolved = _scan_registered(root, routes_root)
        routes.extend(root_routes)
        unresolved.extend(root_unresolved)

    routes.sort(key=lambda row: (row.path, row.method, row.module, row.router_attr, row.source_line))
    unresolved.sort(key=lambda row: (row.module, row.source_line or 0, row.reason))
    route_keys = [(row.method, row.path) for row in routes]
    return InventoryReport(
        modules_declared=len(registered),
        modules_scanned=scanned,
        route_count=len(routes),
        unique_path_count=len({row.path for row in routes}),
        duplicate_route_count=len(route_keys) - len(set(route_keys)),
        unresolved_count=len(unresolved),
        routes=tuple(routes),
        unresolved=tuple(unresolved),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("backend/core/routes_registry.py"))
    parser.add_argument("--routes-root", type=Path, default=Path("backend/routes"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--fail-on-duplicates", action="store_true")
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
        for row in report.unresolved[:20]:
            location = f":{row.source_line}" if row.source_line else ""
            print(f"UNRESOLVED {row.module}{location}: {row.reason}")
        if report.unresolved_count > 20:
            print(f"... {report.unresolved_count - 20} additional unresolved record(s)")
    failed = (args.strict and not report.complete) or (
        args.fail_on_duplicates and report.duplicate_route_count > 0
    )
    return 1 if failed else 0
