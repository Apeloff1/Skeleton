#!/usr/bin/env python3
"""Fail-closed repository audit for the canonical application assembly.

This checker intentionally uses only the Python standard library so it can run
before project dependencies are installed. It verifies cross-file contracts
that ordinary unit tests cannot see when subsystems are edited independently.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        FAILURES.append(message)


def read(relative: str) -> str:
    path = ROOT / relative
    check(path.is_file(), f"missing required file: {relative}")
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def frontend_sources() -> list[Path]:
    base = ROOT / "frontend"
    if not base.is_dir():
        return []
    allowed_suffixes = {".ts", ".tsx", ".js", ".jsx"}
    ignored_parts = {"node_modules", "dist", ".expo", "coverage"}
    return sorted(
        path
        for path in base.rglob("*")
        if path.is_file()
        and path.suffix in allowed_suffixes
        and not ignored_parts.intersection(path.parts)
    )


def audit_manifest() -> None:
    raw = read("skeleton/app/manifest.json")
    if not raw:
        return
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        FAILURES.append(f"invalid skeleton/app/manifest.json: {exc}")
        return

    check(manifest.get("schema_version") == 1, "assembly manifest schema must be 1")
    app = manifest.get("app")
    check(isinstance(app, dict), "assembly manifest app must be an object")
    if not isinstance(app, dict):
        return

    check(app.get("compose_file") == "docker-compose.yml", "canonical compose file drift")
    check(
        app.get("hot_compose_file") == "docker-compose.hot.yml",
        "hot compose overlay drift",
    )
    modes = app.get("modes")
    check(isinstance(modes, dict), "assembly modes must be an object")
    if isinstance(modes, dict):
        check("development" in modes, "development assembly mode missing")
        check("production" in modes, "production assembly mode missing")
        production = modes.get("production", {})
        check(
            isinstance(production, dict)
            and production.get("BUILD_TARGET") == "production"
            and production.get("FRONTEND_BUILD_TARGET") == "production"
            and production.get("FRONTEND_CONTAINER_PORT") == "8080",
            "production assembly mode must select production backend/frontend stages",
        )

    services = manifest.get("services")
    check(isinstance(services, list) and bool(services), "assembly services missing")
    if isinstance(services, list):
        names = [item.get("name") for item in services if isinstance(item, dict)]
        check(len(names) == len(set(names)), "assembly service names must be unique")
        for required in ("frontend", "backend", "skeleton", "mongo"):
            check(required in names, f"canonical service missing: {required}")

    required_paths = manifest.get("required_paths", [])
    check(isinstance(required_paths, list), "required_paths must be a list")
    if isinstance(required_paths, list):
        for relative in required_paths:
            if isinstance(relative, str):
                check((ROOT / relative).exists(), f"manifest required path missing: {relative}")


def audit_no_competing_root_launchers() -> None:
    for relative in ("app.py", "main.py", "server.py"):
        check(
            not (ROOT / relative).exists(),
            f"competing root application launcher is not allowed: {relative}",
        )

    pyproject = read("pyproject.toml")
    check(
        'skeleton = "skeleton.__main__:main"' in pyproject,
        "canonical Python console entrypoint must remain skeleton.__main__:main",
    )


def audit_endpoint_boundary() -> None:
    allowed = {
        (ROOT / "frontend/utils/apiBase.ts").resolve(),
        (ROOT / "frontend/app.config.js").resolve(),
    }
    forbidden = (
        "process.env.EXPO_PUBLIC_BACKEND_URL",
        "process.env.EXPO_PUBLIC_SKELETON_URL",
        "process.env.EXPO_BACKEND_URL",
        "process.env.EXPO_SKELETON_URL",
        "expoConfig?.extra?.EXPO_BACKEND_URL",
        "expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL",
        "expoConfig?.extra?.EXPO_SKELETON_URL",
        "expoConfig?.extra?.EXPO_PUBLIC_SKELETON_URL",
        "http://backend:8001",
        "http://skeleton:8001",
    )

    sources = frontend_sources()
    check(bool(sources), "frontend source inventory is empty")
    for path in sources:
        if path.resolve() in allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in forbidden:
            if token in text:
                relative = path.relative_to(ROOT).as_posix()
                FAILURES.append(
                    f"{relative} bypasses frontend/utils/apiBase.ts with {token!r}"
                )

    resolver = read("frontend/utils/apiBase.ts")
    check("export const API_BASE" in resolver, "canonical backend endpoint export missing")
    check(
        "export const SKELETON_API_BASE" in resolver,
        "canonical Skeleton endpoint export missing",
    )
    check(
        "'http://localhost:8001'" in resolver,
        "backend local fallback must remain localhost:8001",
    )
    check(
        "'http://localhost:8010'" in resolver,
        "Skeleton local fallback must remain localhost:8010",
    )


def audit_compose_modes() -> None:
    base = read("docker-compose.yml")
    hot = read("docker-compose.hot.yml")

    for mount in ("./backend:/app", "./skeleton:/app/skeleton", "./frontend:/app"):
        check(mount not in base, f"source mount leaked into canonical compose: {mount}")

    for mount in (
        "./backend:/app:ro",
        "./skeleton:/app/skeleton:ro",
        "./frontend:/app",
    ):
        check(mount in hot, f"hot-reload overlay missing source mount: {mount}")

    for port in ("8081:8081", "19000:19000", "19001:19001", "19002:19002"):
        check(port not in base, f"dev-only frontend port leaked into canonical compose: {port}")
        check(port in hot, f"hot-reload overlay missing Expo development port: {port}")

    check(
        "target: ${FRONTEND_BUILD_TARGET:-development}" in base,
        "frontend build target must be assembly-selectable",
    )
    check(
        '"${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}"' in base,
        "frontend container port must be assembly-selectable",
    )
    check(
        "EXPO_PUBLIC_BACKEND_URL=${EXPO_PUBLIC_BACKEND_URL:-http://localhost:8001}"
        in base,
        "frontend backend public URL default drift",
    )
    check(
        "EXPO_PUBLIC_SKELETON_URL=${EXPO_PUBLIC_SKELETON_URL:-http://localhost:8010}"
        in base,
        "frontend Skeleton public URL default drift",
    )


def audit_production_ingress() -> None:
    nginx = read("frontend/nginx.conf")
    check("location ^~ /api/v1/" in nginx, "production engine ingress missing")
    check("proxy_pass http://skeleton:8001;" in nginx, "production engine upstream drift")
    check("location ^~ /api/" in nginx, "production backend ingress missing")
    check("proxy_pass http://backend:8001;" in nginx, "production backend upstream drift")

    registry = read("backend/core/routes_registry.py")
    server = read("backend/server.py")
    check("/api/v1" not in registry, "legacy backend route registry claims engine /api/v1")
    check("/api/v1" not in server, "legacy backend server claims engine /api/v1")


def audit_launcher_convergence() -> None:
    launch = read("frontend/components/LaunchCascade.tsx")
    welcome = read("frontend/app/welcome.tsx")
    safe_mode = read("frontend/app/safe-mode.tsx")

    for name, source in (
        ("LaunchCascade", launch),
        ("welcome", welcome),
        ("safe-mode", safe_mode),
    ):
        check(
            "router.replace('/product')" in source,
            f"{name} must converge on /product",
        )

    check("Enter Product" in launch, "launch cascade product label drift")
    check("Enter Product" in welcome, "welcome product label drift")


def audit_product_health_contract() -> None:
    client = read("frontend/src/product/appHealthClient.ts")
    shell = read("frontend/app/product.tsx")
    raw = read("skeleton/app/manifest.json")
    if not raw:
        return
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        return

    services = {
        item.get("name"): item
        for item in manifest.get("services", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    for name, base_symbol in (("backend", "API_BASE"), ("skeleton", "SKELETON_API_BASE")):
        service = services.get(name)
        check(isinstance(service, dict), f"manifest health service missing: {name}")
        if not isinstance(service, dict):
            continue
        path = service.get("health_path")
        check(isinstance(path, str) and bool(path), f"manifest health path missing: {name}")
        if isinstance(path, str) and path:
            expected = f"probe('{name}', {base_symbol}, '{path}'"
            check(expected in client, f"product health client drift for {name}: {path}")

    check("probeAppHealth" in shell, "product shell no longer probes whole-app health")
    check("Application runtime" in shell, "product shell runtime health panel missing")


def audit_product_control_contract() -> None:
    client = read("frontend/src/product/productControlClient.ts")
    ops = read("backend/routes/ops.py")
    registry = read("backend/core/routes_registry.py")

    check(
        "const ROOT = '/api/admin/ops/product-control';" in client,
        "product control client root drift",
    )
    check(
        'router = APIRouter(prefix="/api/admin/ops"' in ops,
        "backend ops prefix drift",
    )
    check('("routes.ops",' in registry, "backend ops router is not registered")

    routes = (
        "/product-control/status",
        "/product-control/deployment-preflight",
        "/product-control/deployments",
        "/product-control/pending",
        "/product-control/audit",
        "/product-control/receipts",
        "/product-control/receipt/{operation_id}/result",
        "/product-control/execute/{seq}",
        "/product-control/execute-pending",
        "/product-control/admit",
    )
    for route in routes:
        check(route in ops, f"product control backend route missing: {route}")


def audit_product_route_registry() -> None:
    registry_text = read("frontend/utils/routeRegistry.ts")
    catalog = read("frontend/src/product/productCatalog.ts")
    registered = set(re.findall(r"path:\s*'([^']+)'", registry_text))

    for route in ("/product", "/capability", "/operation", "/control-plane", "/hub"):
        check(route in registered, f"canonical/compatibility UI route unregistered: {route}")

    literal_targets = re.findall(r"(?:href|legacyHref):\s*'([^']+)'", catalog)
    for target in literal_targets:
        route = target.split("?", 1)[0]
        check(
            route in registered,
            f"product catalog target is absent from route registry: {target}",
        )


def main() -> int:
    audit_manifest()
    audit_no_competing_root_launchers()
    audit_endpoint_boundary()
    audit_compose_modes()
    audit_production_ingress()
    audit_launcher_convergence()
    audit_product_health_contract()
    audit_product_control_contract()
    audit_product_route_registry()

    if FAILURES:
        print(f"App assembly audit failed: {len(FAILURES)} issue(s)", file=sys.stderr)
        for failure in FAILURES:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print(f"App assembly audit passed: {CHECKS} cross-file checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
