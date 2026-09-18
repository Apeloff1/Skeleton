"""Import-free AST helpers shared by structural application audits."""

from __future__ import annotations

import ast
from collections import defaultdict
from importlib.util import find_spec
from pathlib import Path
from typing import Mapping


def literal_str_list(node: ast.AST | None) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    values: list[str] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            values.append(element.value)
    return values


def assigned_all(tree: ast.AST) -> list[str]:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return literal_str_list(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            return literal_str_list(node.value)
    return []


def module_init_path(module: str) -> Path | None:
    spec = find_spec(module)
    if spec is None:
        return None
    if spec.origin and spec.origin not in {"namespace", "built-in"}:
        origin = Path(spec.origin)
        if origin.name == "__init__.py":
            return origin
    locations = spec.submodule_search_locations
    if locations:
        candidate = Path(next(iter(locations))) / "__init__.py"
        if candidate.is_file():
            return candidate
    return None


def public_exports(module: str) -> list[str]:
    init_path = module_init_path(module)
    if init_path is None or not init_path.is_file():
        return []
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except (OSError, SyntaxError):
        return []
    return assigned_all(tree)


def architecture_exports(module: str) -> list[str]:
    from skeleton.architecture import get_package

    package = get_package(module) or {}
    exports = package.get("exports", [])
    if not isinstance(exports, list):
        return []
    return [item for item in exports if isinstance(item, str)]


def architecture_package_exists(module: str) -> bool:
    from skeleton.architecture import get_package

    return get_package(module) is not None


def export_drift(public: list[str], documented: list[str]) -> dict[str, list[str]]:
    public_set = set(public)
    documented_set = set(documented)
    return {
        "missing_from_architecture": [name for name in public if name not in documented_set],
        "missing_from_public": [name for name in documented if name not in public_set],
    }


def genesis_source_path() -> Path | None:
    spec = find_spec("skeleton.genesis")
    if spec is None or not spec.origin:
        return None
    path = Path(spec.origin)
    return path if path.is_file() else None


def parse_genesis_tree() -> ast.AST | None:
    source = genesis_source_path()
    if source is None:
        return None
    try:
        return ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, SyntaxError):
        return None


def genesis_boot_phase_order(tree: ast.AST | None = None) -> list[str]:
    parsed = tree if tree is not None else parse_genesis_tree()
    if parsed is None:
        return []
    for node in parsed.body if isinstance(parsed, ast.Module) else []:
        if not isinstance(node, ast.ClassDef) or node.name != "Genesis":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "boot":
                continue
            phases: list[str] = []
            for stmt in item.body:
                call = stmt.value if isinstance(stmt, ast.Expr) else None
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                    continue
                attr = call.func.attr
                if attr.startswith("_phase_") and len(attr) > 7:
                    phases.append(attr[7:])
            return phases
    return []


def genesis_report_phases(tree: ast.AST | None = None) -> list[str]:
    parsed = tree if tree is not None else parse_genesis_tree()
    if parsed is None:
        return []
    found: list[tuple[int, int, str]] = []
    for node in ast.walk(parsed):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "append" or not node.args:
            continue
        receiver = node.func.value
        if not (
            isinstance(receiver, ast.Attribute)
            and receiver.attr == "phases"
            and isinstance(receiver.value, ast.Attribute)
            and receiver.value.attr == "report"
        ):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found.append((node.lineno, node.col_offset, arg.value))
    ordered: list[str] = []
    seen: set[str] = set()
    for _, _, phase in sorted(found):
        if phase in seen:
            continue
        seen.add(phase)
        ordered.append(phase)
    return ordered


def genesis_wire_map(tree: ast.AST | None = None) -> dict[str, list[str]]:
    parsed = tree if tree is not None else parse_genesis_tree()
    if parsed is None:
        return {}
    found: list[tuple[int, int, str, str]] = []
    for node in ast.walk(parsed):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "_wire" or len(node.args) < 2:
            continue
        phase_node, name_node = node.args[0], node.args[1]
        if not (
            isinstance(phase_node, ast.Constant)
            and isinstance(phase_node.value, str)
            and isinstance(name_node, ast.Constant)
            and isinstance(name_node.value, str)
        ):
            continue
        found.append((node.lineno, node.col_offset, phase_node.value, name_node.value))
    handles: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = defaultdict(set)
    for _, _, phase, handle in sorted(found):
        handles.setdefault(phase, [])
        if handle in seen[phase]:
            continue
        seen[phase].add(handle)
        handles[phase].append(handle)
    return handles


def boot_phase_catalog() -> dict[str, list[str]]:
    from skeleton.architecture import BOOT_PHASES

    catalog: dict[str, list[str]] = {}
    for phase in BOOT_PHASES:
        name = phase.get("phase")
        if not isinstance(name, str) or not name:
            continue
        subsystems: list[str] = []
        for subsystem in phase.get("subsystems", []):
            if not isinstance(subsystem, Mapping):
                continue
            subsystem_name = subsystem.get("name")
            if isinstance(subsystem_name, str) and subsystem_name:
                subsystems.append(subsystem_name)
        catalog[name] = subsystems
    return catalog


_HTTP_METHODS = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "patch": "PATCH"}
_API_PREFIX = "/api/v1"


def _is_require_charter(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "require_charter":
        return True
    return isinstance(func, ast.Attribute) and func.attr == "require_charter"


def _decorator_route(decorator: ast.AST, *, owner_names: tuple[str, ...] = ("router",)) -> tuple[str, str] | None:
    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
        return None
    if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id not in owner_names:
        return None
    method = _HTTP_METHODS.get(decorator.func.attr.lower())
    if method is None or not decorator.args:
        return None
    path_node = decorator.args[0]
    if not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str):
        return None
    return method, path_node.value


def _charter_gated(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    defaults = list(fn.args.defaults) + [item for item in fn.args.kw_defaults if item is not None]
    for default in defaults:
        if _is_require_charter(default):
            return True
        if (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
            and _is_require_charter(default.args[0])
        ):
            return True
    return False


def routes_source_path() -> Path | None:
    spec = find_spec("skeleton.api.routes")
    if spec is None or not spec.origin:
        return None
    path = Path(spec.origin)
    return path if path.is_file() else None


def main_router_handlers() -> list[dict[str, object]]:
    source = routes_source_path()
    if source is None:
        return []
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, SyntaxError):
        return []
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            parsed = _decorator_route(decorator)
            if parsed is None:
                continue
            method, path = parsed
            full_path = path if path.startswith(_API_PREFIX) else f"{_API_PREFIX}{path}"
            full_path = full_path.replace(":path", "").replace(":int", "").replace(":float", "").replace(":uuid", "")
            key = (method, full_path)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "method": method,
                    "path": full_path,
                    "handler": node.name,
                    "charter_gated": _charter_gated(node),
                    "seal_gated": _depends_named(node, "require_seal"),
                    "calls_seal": _calls_named(node, "require_seal"),
                }
            )
    return rows


def architecture_api_routes() -> list[dict[str, object]]:
    from skeleton.architecture import API_ROUTES

    rows: list[dict[str, object]] = []
    for route in API_ROUTES:
        method = route.get("method")
        path = route.get("path")
        if not isinstance(method, str) or not isinstance(path, str):
            continue
        rows.append(
            {
                "method": method.upper(),
                "path": path,
                "protected": bool(route.get("protected")),
            }
        )
    return rows


def module_source_path(module: str) -> Path | None:
    spec = find_spec(module)
    if spec is None or not spec.origin:
        return None
    path = Path(spec.origin)
    return path if path.is_file() else None


def parse_module_tree(module: str) -> ast.AST | None:
    source = module_source_path(module)
    if source is None:
        return None
    try:
        return ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, SyntaxError):
        return None


def assigned_str_tuple(tree: ast.AST | None, name: str) -> list[str]:
    if tree is None or not isinstance(tree, ast.Module):
        return []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return literal_str_list(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return literal_str_list(node.value)
    return []


def path_matches_open_prefix(path: str, prefix: str) -> bool:
    """Mirror GatePolicy prefix matching without importing the API package."""

    current = path or "/"
    pref = (prefix or "").rstrip("/") or "/"
    if pref == "/":
        return current == "/"
    return current == pref or current.startswith(pref + "/")


def hmac_default_open_prefixes() -> list[str]:
    return assigned_str_tuple(parse_module_tree("skeleton.api.middleware"), "DEFAULT_OPEN_PREFIXES")


def hmac_dev_open_prefixes() -> list[str]:
    return assigned_str_tuple(parse_module_tree("skeleton.api.server"), "_DEV_OPEN_PREFIXES")


def hmac_runtime_root_open() -> bool:
    tree = parse_module_tree("skeleton.api.server")
    if tree is None or not isinstance(tree, ast.Module):
        return False
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "_gate_open_prefixes":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.BinOp) or not isinstance(child.op, ast.Add):
                continue
            right = child.right
            if not isinstance(right, ast.Tuple):
                continue
            for element in right.elts:
                if isinstance(element, ast.Constant) and element.value == "/":
                    return True
        return False
    return False


def _is_named_call(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == name:
        return True
    return isinstance(func, ast.Attribute) and func.attr == name


def _is_named_ref(node: ast.AST, name: str) -> bool:
    if isinstance(node, ast.Name) and node.id == name:
        return True
    if isinstance(node, ast.Attribute) and node.attr == name:
        return True
    return _is_named_call(node, name)


def _calls_named(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    for child in ast.walk(fn):
        if child is not fn and _is_named_call(child, name):
            return True
    return False


def _depends_named(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    defaults = list(fn.args.defaults) + [item for item in fn.args.kw_defaults if item is not None]
    for default in defaults:
        if _is_named_ref(default, name):
            return True
        if (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
            and _is_named_ref(default.args[0], name)
        ):
            return True
    return False


def _normalize_handler_path(path: str) -> str:
    full_path = path if path.startswith(_API_PREFIX) else f"{_API_PREFIX}{path}"
    return full_path.replace(":path", "").replace(":int", "").replace(":float", "").replace(":uuid", "")


def module_router_handlers(
    module: str,
    *,
    source: str = "",
    owner_names: tuple[str, ...] = ("router",),
    mount_prefix: str = "/api/v1",
    join_router_prefix: bool = False,
) -> list[dict[str, object]]:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return []
    router_prefix = api_router_prefix(module) if join_router_prefix else ""
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            parsed = _decorator_route(decorator, owner_names=owner_names)
            if parsed is None:
                continue
            method, path = parsed
            full_path = (
                _normalize_handler_path(path)
                if path.startswith(_API_PREFIX)
                else join_url_paths(mount_prefix, router_prefix, path)
            )
            full_path = full_path.replace(":path", "").replace(":int", "").replace(":float", "").replace(":uuid", "")
            key = (method, full_path)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "method": method,
                    "path": full_path,
                    "handler": node.name,
                    "module": module,
                    "source": source or module.rsplit(".", 1)[-1],
                    "charter_gated": _depends_named(node, "require_charter"),
                    "seal_gated": _depends_named(node, "require_seal"),
                    "calls_seal": _calls_named(node, "require_seal"),
                }
            )
    return rows


def sidecar_router_handlers() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for module, source in (
        ("skeleton.api.gameforge_routes", "gameforge"),
        ("skeleton.api.command_routes", "command"),
    ):
        for row in module_router_handlers(module, source=source):
            key = (str(row["method"]), str(row["path"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _dict_str_keys(node: ast.AST | None) -> list[str]:
    if not isinstance(node, ast.Dict):
        return []
    keys: list[str] = []
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.append(key.value)
    return keys


def _assigned_dict(tree: ast.AST | None, name: str) -> ast.Dict | None:
    if tree is None or not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        target_nodes: list[ast.AST] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            target_nodes = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target_nodes = [node.target]
            value = node.value
        if not any(isinstance(target, ast.Name) and target.id == name for target in target_nodes):
            continue
        return value if isinstance(value, ast.Dict) else None
    return None


def scaffold_template_catalog() -> list[dict[str, object]]:
    tree = parse_module_tree("skeleton.developer.scaffold")
    assigned = _assigned_dict(tree, "TEMPLATES")
    if assigned is None:
        return []
    rows: list[dict[str, object]] = []
    for key, value in zip(assigned.keys, assigned.values):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            continue
        description = ""
        files: list[str] = []
        if isinstance(value, ast.Dict):
            for field_key, field_value in zip(value.keys, value.values):
                if not isinstance(field_key, ast.Constant) or not isinstance(field_key.value, str):
                    continue
                if field_key.value == "description" and isinstance(field_value, ast.Constant):
                    description = str(field_value.value)
                elif field_key.value == "files":
                    files = _dict_str_keys(field_value)
        rows.append({"id": key.value, "description": description, "files": files})
    return rows


def architecture_templates() -> list[dict[str, object]]:
    from skeleton.architecture import TEMPLATES

    rows: list[dict[str, object]] = []
    for template in TEMPLATES:
        name = template.get("name")
        if not isinstance(name, str) or not name:
            continue
        files = template.get("files", [])
        rows.append(
            {
                "id": name,
                "description": str(template.get("description") or ""),
                "files": [item for item in files if isinstance(item, str)] if isinstance(files, list) else [],
            }
        )
    return rows


def developer_registry_commands() -> list[str]:
    tree = parse_module_tree("skeleton.developer.commands")
    if tree is None:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "register":
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "_dev_registry":
            continue
        arg = node.args[0]
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            continue
        if arg.value in seen:
            continue
        seen.add(arg.value)
        names.append(arg.value)
    return names


def developer_cli_dispatch_commands() -> list[str]:
    tree = parse_module_tree("skeleton.developer.cli")
    if tree is None:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not node.ops or not node.comparators:
            continue
        if not isinstance(node.ops[0], ast.Eq):
            continue
        left = node.left
        if not isinstance(left, ast.Name) or left.id != "command":
            continue
        comparator = node.comparators[0]
        if not isinstance(comparator, ast.Constant) or not isinstance(comparator.value, str):
            continue
        if comparator.value in seen:
            continue
        seen.add(comparator.value)
        names.append(comparator.value)
    return names


def architecture_cli_commands() -> list[dict[str, object]]:
    from skeleton.architecture import CLI_COMMANDS

    rows: list[dict[str, object]] = []
    for command in CLI_COMMANDS:
        name = command.get("command")
        if not isinstance(name, str) or not name:
            continue
        rows.append(
            {
                "command": name,
                "args": str(command.get("args") or ""),
                "description": str(command.get("description") or ""),
            }
        )
    return rows


def join_url_paths(*parts: str) -> str:
    pieces: list[str] = []
    for part in parts:
        if not isinstance(part, str):
            continue
        text = part.strip()
        if not text or text == "/":
            continue
        pieces.append(text.strip("/"))
    if not pieces:
        return "/"
    return "/" + "/".join(piece for piece in pieces if piece)


def api_router_prefix(module: str, owner: str = "router") -> str:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return ""
    for node in tree.body:
        target: str | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value = node.value
        if target != owner or not isinstance(value, ast.Call):
            continue
        func = value.func
        is_api_router = (isinstance(func, ast.Name) and func.id == "APIRouter") or (
            isinstance(func, ast.Attribute) and func.attr == "APIRouter"
        )
        if not is_api_router:
            continue
        for keyword in value.keywords:
            if (
                keyword.arg == "prefix"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                return keyword.value.value
        return ""
    return ""


def create_app_included_routers() -> list[dict[str, object]]:
    tree = parse_module_tree("skeleton.api.server")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    aliases: dict[str, str] = {}
    rows: list[dict[str, object]] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = node.module
        if not isinstance(node, ast.FunctionDef) or node.name != "create_app":
            continue
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.ImportFrom) and stmt.module:
                for alias in stmt.names:
                    aliases[alias.asname or alias.name] = stmt.module
            if not isinstance(stmt, ast.Call) or not isinstance(stmt.func, ast.Attribute):
                continue
            if stmt.func.attr != "include_router" or not stmt.args:
                continue
            router_arg = stmt.args[0]
            if not isinstance(router_arg, ast.Name):
                continue
            prefix = ""
            for keyword in stmt.keywords:
                if (
                    keyword.arg == "prefix"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    prefix = keyword.value.value
            rows.append(
                {
                    "name": router_arg.id,
                    "module": aliases.get(router_arg.id, ""),
                    "prefix": prefix,
                }
            )
    return rows


_SKIP_MOUNTED_MODULES = frozenset({"skeleton.api.routes", "skeleton.api.gameforge_routes"})


def mounted_router_handlers() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for mount in create_app_included_routers():
        module = str(mount["module"] or "")
        if not module or module in _SKIP_MOUNTED_MODULES:
            continue
        for row in module_router_handlers(
            module,
            source=module.rsplit(".", 1)[-1],
            mount_prefix=str(mount["prefix"] or ""),
            join_router_prefix=True,
        ):
            key = (str(row["method"]), str(row["path"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def cortex_route_handlers() -> list[dict[str, object]]:
    tree = parse_module_tree("skeleton.api.cortex_routes")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "register_routes":
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in child.decorator_list:
                parsed = _decorator_route(decorator, owner_names=("app",))
                if parsed is None:
                    continue
                method, path = parsed
                full_path = _normalize_handler_path(path) if path.startswith(_API_PREFIX) else path
                full_path = full_path.replace(":path", "").replace(":int", "").replace(":float", "").replace(":uuid", "")
                key = (method, full_path)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "method": method,
                        "path": full_path,
                        "handler": child.name,
                        "module": "skeleton.api.cortex_routes",
                        "source": "cortex",
                        "charter_gated": _depends_named(child, "require_charter"),
                        "seal_gated": _depends_named(child, "require_seal"),
                        "calls_seal": _calls_named(child, "require_seal"),
                    }
                )
        break
    return rows


def assigned_str_pairs(tree: ast.AST | None, name: str) -> list[tuple[str, str]]:
    if tree is None or not isinstance(tree, ast.Module):
        return []
    for node in tree.body:
        value: ast.AST | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            value = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
        if value is None:
            continue
        if not isinstance(value, (ast.Tuple, ast.List)):
            return []
        pairs: list[tuple[str, str]] = []
        for element in value.elts:
            if not isinstance(element, (ast.Tuple, ast.List)) or len(element.elts) < 2:
                continue
            left, right = element.elts[0], element.elts[1]
            if (
                isinstance(left, ast.Constant)
                and isinstance(left.value, str)
                and isinstance(right, ast.Constant)
                and isinstance(right.value, str)
            ):
                pairs.append((left.value, right.value))
        return pairs
    return []


def gate_domain_map() -> list[tuple[str, str]]:
    return assigned_str_pairs(parse_module_tree("skeleton.api.middleware"), "DEFAULT_DOMAIN_MAP")


def matching_gate_domain(path: str, domains: list[tuple[str, str]] | None = None) -> str | None:
    mapping = list(domains) if domains is not None else gate_domain_map()
    mapping.sort(key=lambda item: len(item[0]), reverse=True)
    for prefix, domain in mapping:
        if prefix and path_matches_open_prefix(path, prefix):
            return domain
    return None


def _cmd_compare_values(node: ast.Compare) -> list[str]:
    if not node.ops or not node.comparators:
        return []
    left = node.left
    if not isinstance(left, ast.Name) or left.id != "cmd":
        return []
    comparator = node.comparators[0]
    op = node.ops[0]
    if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
        return [comparator.value]
    if isinstance(op, ast.In) and isinstance(comparator, (ast.Tuple, ast.List, ast.Set)):
        return [
            element.value
            for element in comparator.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
    return []


def main_cli_dispatch_commands() -> dict[str, list[str]]:
    tree = parse_module_tree("skeleton.__main__")
    if tree is None or not isinstance(tree, ast.Module):
        return {"commands": [], "aliases": []}
    names: list[str] = []
    aliases: list[str] = []
    seen: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "main":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Compare):
                continue
            for value in _cmd_compare_values(child):
                if value in seen:
                    continue
                seen.add(value)
                if value.startswith("-"):
                    aliases.append(value)
                else:
                    names.append(value)
        break
    return {"commands": names, "aliases": aliases}


def main_cli_help_commands() -> list[str]:
    tree = parse_module_tree("skeleton.__main__")
    if tree is None:
        return []
    doc = ast.get_docstring(tree) or ""
    names: list[str] = []
    in_commands = False
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped == "Commands:":
            in_commands = True
            continue
        if not in_commands:
            continue
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent != 4:
            continue
        token = stripped.split()[0]
        if token and token[0].isalpha():
            names.append(token)
    return names


def assigned_str_constant(tree: ast.AST | None, name: str) -> str | None:
    if tree is None or not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        value: ast.AST | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            value = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def create_app_inline_handlers() -> list[dict[str, object]]:
    tree = parse_module_tree("skeleton.api.server")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "create_app":
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in child.decorator_list:
                parsed = _decorator_route(decorator, owner_names=("app",))
                if parsed is None:
                    continue
                method, path = parsed
                full_path = path if path.startswith("/") else f"/{path}"
                full_path = full_path.replace(":path", "").replace(":int", "").replace(":float", "").replace(":uuid", "")
                key = (method, full_path)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "method": method,
                        "path": full_path,
                        "handler": child.name,
                        "module": "skeleton.api.server",
                        "source": "create_app",
                        "charter_gated": _depends_named(child, "require_charter"),
                        "seal_gated": _depends_named(child, "require_seal"),
                        "calls_seal": _calls_named(child, "require_seal"),
                    }
                )
        break
    return rows


def _require_charter_pair(node: ast.AST) -> tuple[str, str] | None:
    call = node
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Depends"
        and node.args
    ):
        call = node.args[0]
    if not isinstance(call, ast.Call):
        return None
    func = call.func
    is_charter = (isinstance(func, ast.Name) and func.id == "require_charter") or (
        isinstance(func, ast.Attribute) and func.attr == "require_charter"
    )
    if not is_charter or len(call.args) < 2:
        return None
    domain_node, action_node = call.args[0], call.args[1]
    if not isinstance(domain_node, ast.Constant) or not isinstance(domain_node.value, str):
        return None
    if not isinstance(action_node, ast.Constant) or not isinstance(action_node.value, str):
        return None
    return domain_node.value, action_node.value


def _function_charter_pair(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str] | None:
    defaults = list(fn.args.defaults) + [item for item in fn.args.kw_defaults if item is not None]
    for default in defaults:
        pair = _require_charter_pair(default)
        if pair is not None:
            return pair
    return None


def _charter_rows_from_tree(
    tree: ast.AST,
    *,
    module: str,
    source: str,
    owner_names: tuple[str, ...] = ("router",),
    mount_prefix: str = "/api/v1",
    join_router_prefix: bool = False,
    nested: bool = False,
) -> list[dict[str, object]]:
    if not isinstance(tree, ast.Module):
        return []
    router_prefix = api_router_prefix(module) if join_router_prefix else ""
    functions: list[ast.AST] = []
    if nested:
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions.extend(
                    child
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
    else:
        functions = [
            node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for node in functions:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        pair = _function_charter_pair(node)
        if pair is None:
            continue
        domain, action = pair
        for decorator in node.decorator_list:
            parsed = _decorator_route(decorator, owner_names=owner_names)
            if parsed is None:
                continue
            method, path = parsed
            full_path = (
                _normalize_handler_path(path)
                if path.startswith(_API_PREFIX)
                else join_url_paths(mount_prefix, router_prefix, path)
            )
            full_path = full_path.replace(":path", "").replace(":int", "").replace(":float", "").replace(":uuid", "")
            key = (method, full_path)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "method": method,
                    "path": full_path,
                    "handler": node.name,
                    "module": module,
                    "source": source,
                    "domain": domain,
                    "action": action,
                    "key": f"{method} {full_path}",
                }
            )
    return rows


def charter_route_bindings() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    main_tree = parse_module_tree("skeleton.api.routes")
    if main_tree is not None:
        for row in _charter_rows_from_tree(
            main_tree,
            module="skeleton.api.routes",
            source="main",
        ):
            key = (str(row["method"]), str(row["path"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    for module, source in (
        ("skeleton.api.gameforge_routes", "gameforge"),
        ("skeleton.api.command_routes", "command"),
    ):
        tree = parse_module_tree(module)
        if tree is None:
            continue
        for row in _charter_rows_from_tree(tree, module=module, source=source):
            key = (str(row["method"]), str(row["path"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    for mount in create_app_included_routers():
        module = str(mount["module"] or "")
        if not module or module in _SKIP_MOUNTED_MODULES:
            continue
        tree = parse_module_tree(module)
        if tree is None:
            continue
        for row in _charter_rows_from_tree(
            tree,
            module=module,
            source=module.rsplit(".", 1)[-1],
            mount_prefix=str(mount["prefix"] or ""),
            join_router_prefix=True,
        ):
            key = (str(row["method"]), str(row["path"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def command_contract_specs() -> list[dict[str, object]]:
    tree = parse_module_tree("skeleton.application.command_contracts")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    rows: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "CommandSpec":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        auth_required = False
        mutating = False
        for keyword in node.keywords:
            if keyword.arg == "auth_required" and isinstance(keyword.value, ast.Constant):
                auth_required = keyword.value.value is True
            if keyword.arg == "mutating" and isinstance(keyword.value, ast.Constant):
                mutating = keyword.value.value is True
        rows.append(
            {
                "command": node.args[0].value,
                "auth_required": auth_required,
                "mutating": mutating,
            }
        )
    return rows


def runtime_registered_commands() -> list[str]:
    tree = parse_module_tree("skeleton.application.runtime_commands")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "build_runtime_command_service":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call) or not child.args:
                continue
            func = child.func
            if not isinstance(func, ast.Attribute) or func.attr != "register":
                continue
            arg = child.args[0]
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                continue
            if arg.value in seen:
                continue
            seen.add(arg.value)
            names.append(arg.value)
        break
    return names


def live_handler_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    sources = (
        (("main", row) for row in main_router_handlers()),
        (("sidecar", row) for row in sidecar_router_handlers()),
        (("mounted", row) for row in mounted_router_handlers()),
        (("cortex", row) for row in cortex_route_handlers()),
        (("create_app", row) for row in create_app_inline_handlers()),
    )
    for group in sources:
        for source, row in group:
            key = (str(row["method"]), str(row["path"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "method": row["method"],
                    "path": row["path"],
                    "handler": row.get("handler", ""),
                    "source": row.get("source", source),
                    "surface": source,
                    "charter_gated": bool(row.get("charter_gated", False)),
                    "seal_gated": bool(row.get("seal_gated", False)),
                    "calls_seal": bool(row.get("calls_seal", False)),
                }
            )
    return rows


def module_nested_includes(module: str) -> list[dict[str, object]]:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return []
    aliases: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        for alias in node.names:
            aliases[alias.asname or alias.name] = node.module
    rows: list[dict[str, object]] = []
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "include_router" or not call.args:
            continue
        router_arg = call.args[0]
        if not isinstance(router_arg, ast.Name):
            continue
        prefix = ""
        for keyword in call.keywords:
            if (
                keyword.arg == "prefix"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                prefix = keyword.value.value
        rows.append(
            {
                "host_module": module,
                "included_name": router_arg.id,
                "included_module": aliases.get(router_arg.id, ""),
                "prefix": prefix,
            }
        )
    return rows


def nested_router_includes() -> list[dict[str, object]]:
    modules = [str(row["module"]) for row in create_app_included_routers() if row.get("module")]
    modules.append("skeleton.api.command_routes")
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for module in dict.fromkeys(modules):
        for row in module_nested_includes(module):
            key = (str(row["host_module"]), str(row["included_module"] or row["included_name"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _is_environ_get(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
        return False
    receiver = node.func.value
    if isinstance(receiver, ast.Attribute) and receiver.attr == "environ":
        return True
    return isinstance(receiver, ast.Name) and receiver.id == "environ"


def environ_flag_names(module: str) -> list[str]:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return []
    aliases: dict[str, str] = {}
    for node in tree.body:
        target: str | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value = node.value
        if target and isinstance(value, ast.Constant) and isinstance(value.value, str):
            aliases[target] = value.value
    names: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not _is_environ_get(node) or not isinstance(node, ast.Call) or not node.args:
            continue
        arg = node.args[0]
        key: str | None = None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            key = arg.value
        elif isinstance(arg, ast.Name) and arg.id in aliases:
            key = aliases[arg.id]
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(key)
    return names


AUDITED_ENV_MODULES = (
    "skeleton.api.server",
    "skeleton.api.hmac_seal",
    "skeleton.cortex.live",
)


def audited_environ_flags() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for module in AUDITED_ENV_MODULES:
        for name in environ_flag_names(module):
            if name in seen:
                continue
            seen.add(name)
            rows.append({"name": name, "module": module})
    return rows


def literal_str_collection(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in {"frozenset", "set", "tuple", "list"}:
            return literal_str_collection(node.args[0])
    if isinstance(node, ast.Set):
        return [
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
    return literal_str_list(node)


def class_assigned_str_collection(module: str, class_name: str, attr: str) -> list[str]:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            value: ast.AST | None = None
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id == attr:
                        value = child.value
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) and child.target.id == attr:
                value = child.value
            if value is not None:
                return literal_str_collection(value)
        break
    return []


def runtime_capability_view_flags() -> list[str]:
    return assigned_str_tuple(parse_module_tree("skeleton.application.runtime_commands"), "_CAPABILITY_VIEW_FLAGS")


def main_cli_capability_alias_flags() -> list[str]:
    tree = parse_module_tree("skeleton.__main__")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "_cmd_capabilities":
            continue
        for child in node.body:
            value: ast.AST | None = None
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id == "aliases":
                        value = child.value
            if not isinstance(value, ast.Dict):
                continue
            names: list[str] = []
            for key in value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.append(key.value)
            return names
        break
    return []


def main_cli_capability_help_flags() -> list[str]:
    tree = parse_module_tree("skeleton.__main__")
    if tree is None:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for line in (ast.get_docstring(tree) or "").splitlines():
        if "capabilities" not in line or "--" not in line:
            continue
        for token in line.replace("`", " ").split():
            if not token.startswith("--"):
                continue
            name = token[2:].replace("-", "_")
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _idempotency_attrs(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, bool]:
    replay = False
    remember = False
    for child in ast.walk(fn):
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
            continue
        receiver = child.func.value
        if not isinstance(receiver, ast.Name) or receiver.id != "_idempotency":
            continue
        if child.func.attr == "replay":
            replay = True
        elif child.func.attr == "remember":
            remember = True
    return replay, remember


def idempotency_handler_rows() -> list[dict[str, object]]:
    modules = (
        ("skeleton.api.routes", "/api/v1"),
        ("skeleton.api.gameforge_routes", "/api/v1"),
    )
    rows: list[dict[str, object]] = []
    for module, prefix in modules:
        tree = parse_module_tree(module)
        if tree is None or not isinstance(tree, ast.Module):
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            replay, remember = _idempotency_attrs(node)
            if not replay and not remember:
                continue
            for decorator in node.decorator_list:
                parsed = _decorator_route(decorator)
                if parsed is None:
                    continue
                method, path = parsed
                full_path = path if path.startswith(_API_PREFIX) else join_url_paths(prefix, path)
                rows.append(
                    {
                        "key": f"{module}:{node.name}",
                        "module": module,
                        "handler": node.name,
                        "method": method,
                        "path": full_path,
                        "replay": replay,
                        "remember": remember,
                    }
                )
                break
    return rows


def write_admit_mutating_methods() -> list[str]:
    return class_assigned_str_collection("skeleton.api.admit_write", "WriteAdmitMiddleware", "_MUTATING")


AUDITED_GATE_LIMIT_MODULES = (
    "skeleton.api.request_bounds",
    "skeleton.api.middleware",
)


def audited_gate_limit_flags() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for module in AUDITED_GATE_LIMIT_MODULES:
        tree = parse_module_tree(module)
        names = list(environ_flag_names(module))
        if tree is not None:
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args or not _is_named_call(node, "_positive_limit"):
                    continue
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    names.append(arg.value)
        for name in names:
            if not name.startswith("SKELETON_GATE_") or name in seen:
                continue
            seen.add(name)
            rows.append({"name": name, "module": module})
    return rows


def main_cli_shared_command_map() -> list[dict[str, object]]:
    tree = parse_module_tree("skeleton.__main__")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "main":
            continue
        for child in node.body:
            if not isinstance(child, ast.If):
                continue
            cli_names = _cmd_compare_values(child.test) if isinstance(child.test, ast.Compare) else []
            spec = ""
            dispatcher = False
            found = False
            for stmt in child.body:
                call = stmt.value if isinstance(stmt, ast.Return) else None
                if not isinstance(call, ast.Call) or not call.args:
                    continue
                func = call.func
                if not isinstance(func, ast.Name) or func.id != "_cmd_shared_command":
                    continue
                found = True
                arg = call.args[0]
                if isinstance(arg, ast.Name) and arg.id == "rest":
                    dispatcher = True
                elif isinstance(arg, (ast.List, ast.Tuple)) and arg.elts:
                    first = arg.elts[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        spec = first.value
                break
            if not found:
                continue
            for name in cli_names:
                if name in seen:
                    continue
                seen.add(name)
                rows.append(
                    {
                        "cli": name,
                        "spec": spec,
                        "dispatcher": dispatcher,
                    }
                )
        break
    return rows


def install_gate_middleware_order() -> list[str]:
    tree = parse_module_tree("skeleton.api.middleware")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    names: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "install_gate":
            continue
        for child in node.body:
            call = child.value if isinstance(child, ast.Expr) else None
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            if not isinstance(func, ast.Attribute) or func.attr != "add_middleware" or not call.args:
                continue
            arg = call.args[0]
            if isinstance(arg, ast.Name):
                names.append(arg.id)
        break
    return names


_ALLOW_LIST_CATALOGS = frozenset({"MATERIALISE_TARGETS", "PROGRESSION_CURVES"})
_ALLOW_LIST_MODULES = (
    "skeleton.api.routes",
    "skeleton.application.runtime_commands",
)


def allow_list_usages() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for module in _ALLOW_LIST_MODULES:
        tree = parse_module_tree(module)
        if tree is None or not isinstance(tree, ast.Module):
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            catalogs: list[str] = []
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                for keyword in child.keywords:
                    if keyword.arg != "allowed":
                        continue
                    value = keyword.value
                    if isinstance(value, ast.Name) and value.id in _ALLOW_LIST_CATALOGS:
                        catalogs.append(value.id)
            for catalog in dict.fromkeys(catalogs):
                key = (module, node.name, catalog)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "key": f"{module}:{node.name}",
                        "module": module,
                        "handler": node.name,
                        "catalog": catalog,
                    }
                )
    return rows


AUDITED_VERSION_NAMES = (
    ("skeleton", "__version__"),
    ("skeleton.architecture", "ARCHITECTURE_VERSION"),
    ("skeleton.application.runtime_commands", "APP_VERSION"),
    ("skeleton.setup_config", "VERSION"),
)


def fastapi_version_literals() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module in ("skeleton.api.server", "skeleton.deploy.harness"):
        tree = parse_module_tree(module)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_named_call(node, "FastAPI"):
                continue
            for keyword in node.keywords:
                if keyword.arg != "version":
                    continue
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    rows.append({"source": f"{module}:FastAPI.version", "value": keyword.value.value})
    return rows


def class_assigned_str_constant(module: str, class_name: str, attr: str) -> str | None:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            value: ast.AST | None = None
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) and child.target.id == attr:
                value = child.value
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id == attr:
                        value = child.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
        break
    return None


def version_identity_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module, name in AUDITED_VERSION_NAMES:
        rows.append(
            {
                "source": f"{module}:{name}",
                "value": assigned_str_constant(parse_module_tree(module), name) or "",
            }
        )
    settings = class_assigned_str_constant("skeleton.config.settings", "Settings", "version")
    rows.append({"source": "skeleton.config.settings:Settings.version", "value": settings or ""})
    rows.extend(fastapi_version_literals())
    return rows


def public_dev_surface_tokens() -> list[str]:
    tree = parse_module_tree("skeleton.api.server")
    if tree is None or not isinstance(tree, ast.Module):
        return []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "_public_dev_surfaces_enabled":
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Set):
                return literal_str_collection(child)
        break
    return []


def enum_str_assignments(module: str, class_name: str) -> list[dict[str, str]]:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return []
    rows: list[dict[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            member = ""
            value: ast.AST | None = None
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        member = target.id
                        value = child.value
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                member = child.target.id
                value = child.value
            if member and isinstance(value, ast.Constant) and isinstance(value.value, str):
                rows.append({"member": member, "value": value.value})
        break
    return rows


def session_mode_identity_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module in ("skeleton.jeeves.core", "skeleton.jeeves.llm_core"):
        for item in enum_str_assignments(module, "SessionMode"):
            rows.append(
                {
                    "source": f"{module}:SessionMode.{item['member']}",
                    "member": item["member"],
                    "value": item["value"],
                }
            )
    return rows


AUDITED_CODENAME_NAMES = (
    ("skeleton", "__codename__"),
    ("skeleton.architecture", "CODENAME"),
    ("skeleton.setup_config", "CODENAME"),
)


def nested_handler_return_str(module: str, outer: str, key: str) -> str | None:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != outer:
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for stmt in child.body:
                if not isinstance(stmt, ast.Return) or not isinstance(stmt.value, ast.Dict):
                    continue
                for dict_key, dict_value in zip(stmt.value.keys, stmt.value.values):
                    if not isinstance(dict_key, ast.Constant) or dict_key.value != key:
                        continue
                    if isinstance(dict_value, ast.Constant) and isinstance(dict_value.value, str):
                        return dict_value.value
                break
        break
    return None


def codename_identity_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module, name in AUDITED_CODENAME_NAMES:
        rows.append(
            {
                "source": f"{module}:{name}",
                "value": assigned_str_constant(parse_module_tree(module), name) or "",
            }
        )
    application = nested_handler_return_str(
        "skeleton.application.runtime_commands",
        "_configuration_handler",
        "application",
    )
    rows.append(
        {
            "source": "skeleton.application.runtime_commands:configuration.application",
            "value": application or "",
        }
    )
    return rows


AUDITED_CONTRACT_VERSION_NAMES = (
    ("skeleton.application.command_contracts", "CONTRACT_VERSION"),
)


def contract_version_identity_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module, name in AUDITED_CONTRACT_VERSION_NAMES:
        rows.append(
            {
                "source": f"{module}:{name}",
                "value": assigned_str_constant(parse_module_tree(module), name) or "",
            }
        )
    advertised = nested_handler_return_str(
        "skeleton.application.runtime_commands",
        "_configuration_handler",
        "command_contract_version",
    )
    if advertised is not None:
        rows.append(
            {
                "source": "skeleton.application.runtime_commands:configuration.command_contract_version",
                "value": advertised,
            }
        )
    return rows


def _numeric_constant(node: ast.AST | None) -> int | float | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _numeric_constant(node.operand)
        return None if inner is None else -inner
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


def assigned_numeric_constant(tree: ast.AST | None, name: str) -> int | float | None:
    if tree is None or not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        value: ast.AST | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            value = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
        number = _numeric_constant(value)
        if number is not None:
            return number
    return None


def class_field_numeric_default(module: str, class_name: str, attr: str) -> int | float | None:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            value: ast.AST | None = None
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) and child.target.id == attr:
                value = child.value
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id == attr:
                        value = child.value
            number = _numeric_constant(value)
            if number is not None:
                return number
        break
    return None


def function_arg_numeric_default(
    module: str,
    func_name: str,
    arg_name: str,
    *,
    class_name: str | None = None,
) -> int | float | None:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return None
    bodies: list[ast.stmt] = list(tree.body)
    if class_name is not None:
        bodies = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                bodies = list(node.body)
                break
    for node in bodies:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != func_name:
            continue
        args = node.args
        defaults = list(args.defaults)
        positional = list(args.posonlyargs) + list(args.args)
        bound = positional[len(positional) - len(defaults) :] if defaults else []
        for arg, default in zip(bound, defaults):
            if arg.arg == arg_name:
                return _numeric_constant(default)
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            if arg.arg == arg_name:
                return _numeric_constant(default)
        break
    return None


def ttl_identity_rows() -> list[dict[str, object]]:
    hmac = assigned_numeric_constant(parse_module_tree("skeleton.api.hmac_seal"), "DEFAULT_TTL_SECS")
    entry = class_field_numeric_default("skeleton.api.idempotency", "IdempotencyEntry", "ttl_seconds")
    guard = function_arg_numeric_default(
        "skeleton.api.idempotency",
        "__init__",
        "default_ttl",
        class_name="IdempotencyGuard",
    )
    return [
        {"source": "skeleton.api.hmac_seal:DEFAULT_TTL_SECS", "value": hmac},
        {"source": "skeleton.api.idempotency:IdempotencyEntry.ttl_seconds", "value": entry},
        {"source": "skeleton.api.idempotency:IdempotencyGuard.default_ttl", "value": guard},
    ]


