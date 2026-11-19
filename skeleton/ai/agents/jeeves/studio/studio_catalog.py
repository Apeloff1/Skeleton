"""Execute every studio module that no sibling imports.

The catalog lives in both studio trees. ``PACKAGE`` follows the importing
package so each tree calls its own siblings.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import types
from pathlib import Path
from typing import Any, Dict, Final, List, Literal, Tuple, Union, get_args, get_origin, get_type_hints

EXCLUDED = frozenset({
    "studio_catalog",
    "integrated_studio",
    "pipeline_runner",
    "studio_cli",
    "pipeline_selftest",
    "completionist_selftest",
    "operational_entry",
    "e2e_smoke",
})

PACKAGE = __package__ or "skeleton.jeeves.studio"

_RICH_DICT = {
    "optical": 0.95,
    "fidelity": 0.96,
    "x": 1,
    "y": 1,
    "key": "studio",
    "value": 1,
    "duration": 1.0,
    "rooms": [{"id": 1, "biome": "ash", "difficulty": 0.5}],
}


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _imported_sibling_names(root: Path) -> set[str]:
    names: set[str] = set()
    for path in root.glob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level != 1:
                continue
            if node.module:
                names.add(node.module.split(".")[0])
            else:
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
    return names


def orphan_names() -> list[str]:
    root = _package_dir()
    imported = _imported_sibling_names(root)
    found: list[str] = []
    for path in sorted(root.glob("*.py")):
        name = path.stem
        if name.startswith("_") or name in EXCLUDED or name in imported:
            continue
        found.append(name)
    return found


def _is_plain_dict(hint: Any) -> bool:
    if hint in (dict, Dict):
        return True
    origin = get_origin(hint)
    return origin in (dict, Dict) and not get_args(hint)


def _is_rich_dict(hint: Any) -> bool:
    origin = get_origin(hint)
    args = get_args(hint)
    if origin not in (dict, Dict) or len(args) != 2:
        return False
    key_type, value_type = args
    return key_type is str and value_type is Any


def _synthetic(hint: Any, depth: int = 0) -> Any:
    if depth > 4 or hint is Any or hint is inspect.Parameter.empty or hint is None:
        return dict(_RICH_DICT) if hint is Any else None
    origin = get_origin(hint)
    if origin in (Union, getattr(types, "UnionType", ())):
        choices = [item for item in get_args(hint) if item is not type(None)]
        return _synthetic(choices[0], depth + 1) if choices else None
    if origin is Literal:
        args = get_args(hint)
        return args[0] if args else None
    if origin in (Final,):
        args = get_args(hint)
        return _synthetic(args[0], depth + 1) if args else None
    if getattr(origin, "__name__", "") == "Annotated" or str(origin).endswith("Annotated"):
        args = get_args(hint)
        return _synthetic(args[0], depth + 1) if args else None
    if _is_rich_dict(hint):
        return dict(_RICH_DICT)
    if origin in (dict, Dict):
        args = get_args(hint)
        if len(args) == 2 and _is_plain_dict(args[1]):
            return {"nested": {}}
        if len(args) == 2:
            return {"nested": _synthetic(args[1], depth + 1)}
        return {}
    if _is_plain_dict(hint):
        return {}
    if origin in (list, List) or hint in (list, List):
        args = get_args(hint)
        inner = args[0] if args else Any
        return [_synthetic(inner, depth + 1)]
    if origin in (tuple, Tuple) or hint in (tuple, Tuple):
        args = get_args(hint)
        if not args:
            return ()
        if len(args) == 2 and args[1] is Ellipsis:
            return (_synthetic(args[0], depth + 1),)
        return tuple(_synthetic(item, depth + 1) for item in args if item is not Ellipsis)
    if origin in (set, frozenset) or hint in (set, frozenset):
        args = get_args(hint)
        inner = args[0] if args else str
        value = _synthetic(inner, depth + 1)
        try:
            built = {value}
        except TypeError:
            built = {"studio"}
        if hint is frozenset or origin is frozenset:
            return frozenset(built)
        return built
    if hint is bool:
        return False
    if hint is int:
        return 1
    if hint is float:
        return 0.95
    if hint is str:
        return "studio"
    if hint is bytes:
        return b"studio"
    if isinstance(hint, type):
        try:
            import enum
            if issubclass(hint, enum.Enum):
                return next(iter(hint))
        except Exception:
            pass
        if hint in (int, float, str, bool, bytes):
            return _synthetic(hint, depth + 1)
        try:
            return hint()
        except Exception:
            return None
    return None


def _compatible(value: Any, hint: Any) -> bool:
    if hint is inspect.Parameter.empty or hint is Any or hint is None:
        return True
    origin = get_origin(hint)
    if origin in (Union, getattr(types, "UnionType", ())):
        return any(_compatible(value, item) for item in get_args(hint))
    if origin is Literal:
        return value in get_args(hint)
    if _is_plain_dict(hint) or _is_rich_dict(hint) or origin in (dict, Dict):
        return isinstance(value, dict)
    if origin in (list, List) or hint in (list, List):
        return isinstance(value, list)
    if origin in (tuple, Tuple) or hint in (tuple, Tuple):
        return isinstance(value, tuple)
    if isinstance(hint, type):
        if hint is int and isinstance(value, bool):
            return False
        return isinstance(value, hint)
    return True


def _hints(func: Any, module: Any) -> dict[str, Any]:
    globalns = getattr(func, "__globals__", None)
    localns = vars(module) if module is not None else None
    try:
        return get_type_hints(func, globalns=globalns, localns=localns)
    except Exception:
        try:
            return get_type_hints(func)
        except Exception:
            return {}


def _bind(func: Any, context: Dict[str, Any], module: Any) -> tuple[list[Any], dict[str, Any]]:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return [], {}
    hints = _hints(func, module)
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    for name, param in signature.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        hint = hints.get(name, param.annotation)
        if name in context and _compatible(context[name], hint):
            value = context[name]
        elif param.default is not inspect.Parameter.empty:
            continue
        else:
            value = _synthetic(hint)
        if param.kind == param.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[name] = value
    return positional, keywords


def _call(func: Any, context: Dict[str, Any], module: Any, bound: Any = None) -> None:
    target = func if bound is None else bound
    positional, keywords = _bind(func, context, module)
    result = target(*positional, **keywords)
    if inspect.iscoroutine(result):
        result.close()


def _public_methods(cls: type) -> list[tuple[str, Any]]:
    methods: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for klass in cls.__mro__:
        if klass is object:
            continue
        for name, value in klass.__dict__.items():
            if name.startswith("_") or name in seen:
                continue
            func = value
            if isinstance(value, (staticmethod, classmethod)):
                func = value.__func__
            if not inspect.isfunction(func):
                continue
            seen.add(name)
            methods.append((name, func))
    return methods


def _exercise(module: Any, context: Dict[str, Any]) -> None:
    for name, obj in list(vars(module).items()):
        if name.startswith("_"):
            continue
        if inspect.isfunction(obj) and getattr(obj, "__module__", None) == module.__name__:
            _call(obj, context, module)
        elif inspect.isclass(obj) and getattr(obj, "__module__", None) == module.__name__:
            init = getattr(obj, "__init__", object.__init__)
            positional, keywords = ([], {})
            if init is not object.__init__:
                positional, keywords = _bind(init, context, module)
            instance = obj(*positional, **keywords)
            for method_name, func in _public_methods(obj):
                _call(func, context, module, bound=getattr(instance, method_name))


def _run_module(name: str, context: Dict[str, Any]) -> Dict[str, Any]:
    try:
        module = importlib.import_module(f"{PACKAGE}.{name}")
        _exercise(module, context)
    except Exception:
        return {"ok": False, "name": name, "reason": "call_failed"}
    return {"ok": True, "name": name, "reason": "ok"}


def run_orphans(context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    supplied = dict(context or {})
    names = orphan_names()
    failed: list[str] = []
    ran = 0
    for name in names:
        outcome = _run_module(name, supplied)
        if outcome["ok"]:
            ran += 1
        else:
            failed.append(name)
    ok = not failed
    return {
        "ok": ok,
        "count": len(names),
        "ran": ran,
        "failed": failed[:12],
        "reason": "ok" if ok else "modules_failed",
        "schema": "skeleton.studio.catalog.v1",
    }
