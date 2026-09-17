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


def _decorator_route(decorator: ast.AST) -> tuple[str, str] | None:
    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
        return None
    if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "router":
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


def module_router_handlers(module: str, *, source: str = "") -> list[dict[str, object]]:
    tree = parse_module_tree(module)
    if tree is None or not isinstance(tree, ast.Module):
        return []
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            parsed = _decorator_route(decorator)
            if parsed is None:
                continue
            method, path = parsed
            full_path = _normalize_handler_path(path)
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
