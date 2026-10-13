"""Bounded offline source-based frontend/API route contract reconnaissance.

No application server is started. Only literal route declarations/calls are
matched. Dynamic routes, router composition, reverse proxies, authentication,
request body contracts and actual deployment remain independently unverified.
"""
from __future__ import annotations

import ast
from hashlib import sha256
import re

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, digest,
)

SCHEMA = "skeleton.ai.jeeves_crossplane_route_scout.v1"
MAX_PATHS = 48
MAX_BYTES = 200_000
MAX_ENDPOINTS = 2048
MAX_ROUTE_LEN = 240
METHODS = frozenset(("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"))
FRONT_CALL = re.compile(
    r"""\b(?:fetch\s*\(|(?:axios|api|client|http)\s*\.\s*
    (?P<method>get|post|put|patch|delete|head|options)\s*\()
    \s*['\"](?P<path>[/][^'\"]{0,240})['\"]""",
    re.IGNORECASE | re.VERBOSE,
)


def _path(value):
    if type(value) is not str or not 1 <= len(value) <= MAX_ROUTE_LEN:
        return None
    if (".." in value or "\x00" in value or "\\" in value or
        "://" in value or "?" in value or "#" in value or
        "${" in value):
        return None
    if not value.startswith("/") or "//" in value:
        return None
    return value.rstrip("/") or "/"


def _str_literal(value):
    if isinstance(value, ast.Constant) and type(value.value) is str:
        return value.value
    return None


def _python_api(path, content):
    try:
        tree = ast.parse(content, filename=path)
    except (SyntaxError, RecursionError, ValueError):
        return [], "python_parse_error"
    prefixes = {}
    for item in tree.body:
        if (isinstance(item, (ast.Assign, ast.AnnAssign)) and
            isinstance(item.value, ast.Call) and
            isinstance(item.value.func, ast.Name) and
            item.value.func.id == "APIRouter"):
            prefix = next((_str_literal(kw.value) for kw in item.value.keywords
                           if kw.arg == "prefix"), "")
            names = (item.targets if isinstance(item, ast.Assign)
                     else [item.target])
            for name in names:
                if isinstance(name, ast.Name) and prefix is not None:
                    prefixes[name.id] = prefix
    results = []
    for item in tree.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in item.decorator_list:
            if (not isinstance(decorator, ast.Call) or
                not isinstance(decorator.func, ast.Attribute)):
                continue
            method = decorator.func.attr.upper()
            if method not in METHODS:
                continue
            raw = _str_literal(decorator.args[0]) if decorator.args else next(
                (_str_literal(kw.value) for kw in decorator.keywords
                 if kw.arg in ("path", "url")), None)
            if raw is None:
                continue
            root = decorator.func.value
            prefix = prefixes.get(root.id, "") if isinstance(root, ast.Name) else ""
            route = _path(prefix + raw)
            if route is None:
                continue
            results.append({
                "source": path,
                "method": method, "path": route,
                "owner_function": item.name,
                "literal_decorator": True,
                "runtime_registered": False,
            })
    return results, "parsed"


def _frontend_calls(path, content):
    result = []
    dynamic_unresolved = 0
    for found in FRONT_CALL.finditer(content):
        method = found.group("method")
        route = _path(found.group("path"))
        if route is None:
            dynamic_unresolved += 1
            continue
        # fetch(url) defaults to GET. Its second options argument, if any,
        # may override the method and therefore cannot be claimed static.
        declared_method = method.upper() if method else "UNKNOWN_FETCH_OPTIONS"
        result.append({
            "source": path, "method": declared_method,
            "path": route, "literal_call": True,
            "runtime_executed": False,
        })
    return result, dynamic_unresolved


def _compare_routes(frontend, backend):
    offered = {(row["method"], row["path"]) for row in backend}
    by_path = {row["path"] for row in backend}
    matches = []
    missing = []
    uncertain = []
    for row in frontend:
        if row["method"] == "UNKNOWN_FETCH_OPTIONS":
            uncertain.append({**row, "reason": "fetch_options_method_not_statically_proven"})
        elif (row["method"], row["path"]) in offered:
            matches.append({**row, "matching_backend_declaration": True,
                            "runtime_binding_verified": False})
        elif row["path"] in by_path:
            missing.append({**row, "reason": "literal_http_method_mismatch"})
        else:
            missing.append({**row, "reason": "no_literal_backend_declaration"})
    return matches, missing, uncertain


class JeevesAPIBindingScout:
    """Works on selected, explicitly readable source files only."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical appwide inventory required")
        inventory._require_scanned()
        self.inv = inventory

    def inspect(self, *, backend_paths, frontend_paths, expected_snapshot=None,
                expected_sources=None):
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("stale source routing inventory")
        if (type(backend_paths) is not list or type(frontend_paths) is not list
            or not backend_paths or not frontend_paths
            or len(backend_paths) + len(frontend_paths) > MAX_PATHS):
            raise JeevesAppwideError("bounded explicit backend and frontend path groups")
        selected = backend_paths + frontend_paths
        if any(type(x) is not str for x in selected) or len(set(selected)) != len(selected):
            raise JeevesAppwideError("unique typed routing source paths required")
        if expected_sources is not None and (
            type(expected_sources) is not dict or set(expected_sources) != set(selected)):
            raise JeevesAppwideError("complete selected-source identity map required")
        backend = []
        frontend = []
        receipts = []
        unknown_syntax = 0
        for path in selected:
            if not path.endswith((".py", ".js", ".jsx", ".ts", ".tsx")):
                raise JeevesAppwideError("unrecognized reviewed route source language")
            if path in backend_paths and not path.endswith(".py"):
                raise JeevesAppwideError("Python FastAPI backend source required")
            if path in frontend_paths and not path.endswith((".js", ".jsx", ".ts", ".tsx")):
                raise JeevesAppwideError("JS/TS frontend source required")
            content = self.inv._safe_file(path, max_size=MAX_BYTES)
            content_sha = sha256(content.encode("utf-8")).hexdigest()
            if expected_sources is not None and expected_sources[path] != content_sha:
                raise JeevesAppwideError("source SHA differs from accepted routing plan")
            if path in backend_paths:
                candidates, status = _python_api(path, content)
                backend.extend(candidates)
                if status != "parsed":
                    unknown_syntax += 1
            else:
                calls, unknown = _frontend_calls(path, content)
                frontend.extend(calls)
                unknown_syntax += unknown
            receipts.append({
                "path": path, "sha256": content_sha,
                "source_bytes": len(content.encode("utf-8")),
            })
            if len(backend) + len(frontend) > MAX_ENDPOINTS:
                raise JeevesAppwideError("route census exceeds bounded static scope")
        backend.sort(key=lambda x: (x["source"], x["method"], x["path"]))
        frontend.sort(key=lambda x: (x["source"], x["method"], x["path"]))
        matches, missing, uncertain = _compare_routes(frontend, backend)
        body = {
            "schema": SCHEMA,
            "inventory_snapshot": self.inv._digest,
            "source_receipts": sorted(receipts, key=lambda x: x["path"]),
            "backend_declared_routes": backend,
            "frontend_literal_calls": frontend,
            "literal_matches": matches,
            "unmatched_literal_calls": missing,
            "indeterminate_calls": uncertain,
            "unresolved_or_syntax_errors": unknown_syntax,
            "backend_declared_count": len(backend),
            "frontend_literal_count": len(frontend),
            "literal_match_count": len(matches),
            "literal_mismatch_count": len(missing),
            "dynamic_routes_not_claimed": True,
            "frontend_fetch_options_not_assumed_get": True,
            "no_backend_or_frontend_code_executed": True,
            "application_binding_complete": False,
        }
        return {**body, "digest": digest(body)}
