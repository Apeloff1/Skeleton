#!/usr/bin/env python3
"""Fail-closed repository audit for the canonical application assembly.

This checker intentionally uses only the Python standard library so it can run
before project dependencies are installed. It verifies cross-file contracts
that ordinary unit tests cannot see when subsystems are edited independently.
"""

from __future__ import annotations

import ast
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
        known_names = {name for name in names if isinstance(name, str)}
        for required in ("frontend", "backend", "skeleton", "mongo"):
            check(required in names, f"canonical service missing: {required}")

        dependencies: dict[str, tuple[str, ...]] = {}
        for item in services:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"]
            raw_deps = item.get("depends_on", [])
            check(isinstance(raw_deps, list), f"service {name} depends_on must be a list")
            deps = tuple(dep for dep in raw_deps if isinstance(dep, str)) if isinstance(raw_deps, list) else ()
            check(
                set(deps).issubset(known_names),
                f"service {name} references unknown dependencies: {sorted(set(deps) - known_names)}",
            )
            dependencies[name] = deps

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str, trail: tuple[str, ...]) -> None:
            if name in visited:
                return
            if name in visiting:
                cycle = " -> ".join((*trail, name))
                FAILURES.append(f"assembly service dependency cycle: {cycle}")
                return
            visiting.add(name)
            for dependency in dependencies.get(name, ()):
                visit(dependency, (*trail, name))
            visiting.remove(name)
            visited.add(name)

        for name in sorted(dependencies):
            visit(name, ())

        default_services = app.get("default_services", [])
        full_services = app.get("full_services", [])
        check(isinstance(default_services, list), "default_services must be a list")
        check(isinstance(full_services, list), "full_services must be a list")
        if isinstance(default_services, list) and isinstance(full_services, list):
            check(
                set(default_services).issubset(known_names),
                f"default profile references unknown services: {sorted(set(default_services) - known_names)}",
            )
            check(
                set(full_services).issubset(known_names),
                f"full profile references unknown services: {sorted(set(full_services) - known_names)}",
            )
            check(
                set(default_services).issubset(set(full_services)),
                "full profile must contain every default service",
            )

    required_paths = manifest.get("required_paths", [])
    check(isinstance(required_paths, list), "required_paths must be a list")
    if isinstance(required_paths, list):
        for relative in required_paths:
            if isinstance(relative, str):
                check((ROOT / relative).exists(), f"manifest required path missing: {relative}")



def _compose_service_names(source: str) -> set[str]:
    names: set[str] = set()
    inside_services = False
    for line in source.splitlines():
        if line == "services:":
            inside_services = True
            continue
        if inside_services and line and not line.startswith(" "):
            break
        if not inside_services:
            continue
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            names.add(match.group(1))
    return names


def audit_topology_alignment() -> None:
    raw_manifest = read("skeleton/app/manifest.json")
    compose = read("docker-compose.yml")
    frontend_config = read("frontend/app.json")
    if not raw_manifest or not compose or not frontend_config:
        return

    try:
        manifest = json.loads(raw_manifest)
        expo = json.loads(frontend_config)
    except json.JSONDecodeError as exc:
        FAILURES.append(f"application identity/topology JSON invalid: {exc}")
        return

    manifest_services = {
        item.get("name")
        for item in manifest.get("services", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    compose_services = _compose_service_names(compose)
    check(
        manifest_services == compose_services,
        f"manifest/compose service drift: manifest={sorted(manifest_services)} compose={sorted(compose_services)}",
    )

    app = manifest.get("app", {})
    expo_config = expo.get("expo", {})
    manifest_name = app.get("name") if isinstance(app, dict) else None
    expo_name = expo_config.get("name") if isinstance(expo_config, dict) else None
    check(
        isinstance(manifest_name, str) and bool(manifest_name.strip()),
        "assembly manifest application name missing",
    )
    check(
        expo_name == manifest_name,
        f"frontend display identity drift: expo={expo_name!r} manifest={manifest_name!r}",
    )
    manifest_version = app.get("version") if isinstance(app, dict) else None
    expo_version = expo_config.get("version") if isinstance(expo_config, dict) else None
    check(
        expo_version == manifest_version,
        f"frontend application version drift: expo={expo_version!r} manifest={manifest_version!r}",
    )
    public_contract = app.get("public_contract") if isinstance(app, dict) else None
    check(isinstance(public_contract, dict), "manifest public application contract missing")
    if isinstance(public_contract, dict):
        check(public_contract.get("prefix") == "/api/app", "public application contract prefix drift")
        for name in ("bootstrap", "status", "ready"):
            value = public_contract.get(name)
            check(
                isinstance(value, str) and value.startswith("/"),
                f"public application contract route invalid: {name}={value!r}",
            )


def audit_backend_public_identity() -> None:
    health = read("backend/routes/health.py")
    server = read("backend/server.py")

    check('"name": "Skeleton Application API"' in health, "backend root identity drift")
    check('"legacy_name": "CodeDock Quantum Nexus"' in health, "legacy backend identity compatibility marker missing")
    check('SYSTEM_VERSION = "11.0.0"' in health, "backend health component version drift")
    check('title="Skeleton Application API"' in server, "backend OpenAPI title drift")
    check('logging.getLogger("Skeleton.Backend")' in server, "backend logger identity drift")


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
        "Constants.CANONICAL_API_BASE",
        "process.env.CANONICAL_API_BASE",
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



def _provider_registry_names(tree: ast.AST) -> set[str]:
    """Return all local names that resolve to ProviderRegistry."""

    names = {"ProviderRegistry"}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "ProviderRegistry":
                        local = alias.asname or alias.name
                        if local not in names:
                            names.add(local)
                            changed = True
                continue

            value: ast.AST | None = None
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign):
                value = node.value
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                value = node.value
                targets = [node.target]
            if value is None:
                continue

            registry_value = (
                isinstance(value, ast.Name) and value.id in names
            ) or (
                isinstance(value, ast.Attribute)
                and value.attr == "ProviderRegistry"
            )
            if not registry_value:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.add(target.id)
                    changed = True
    return names


def _provider_registry_activation_aliases(
    tree: ast.AST,
    names: set[str],
) -> set[str]:
    """Return local callables assigned from ProviderRegistry.from_env."""

    aliases: set[str] = set()
    for node in ast.walk(tree):
        value: ast.AST | None = None
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        if not isinstance(value, ast.Attribute) or value.attr != "from_env":
            continue
        receiver = value.value
        registry_receiver = (
            isinstance(receiver, ast.Name) and receiver.id in names
        ) or (
            isinstance(receiver, ast.Attribute)
            and receiver.attr == "ProviderRegistry"
        )
        if not registry_receiver:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                aliases.add(target.id)
    return aliases


def _is_provider_registry_from_env_call(
    node: ast.Call,
    names: set[str],
    activation_aliases: set[str] | None = None,
) -> bool:
    aliases = activation_aliases or set()
    func = node.func

    if isinstance(func, ast.Name):
        return func.id in aliases

    if isinstance(func, ast.Attribute) and func.attr == "from_env":
        receiver = func.value
        if isinstance(receiver, ast.Name):
            return receiver.id in names
        return (
            isinstance(receiver, ast.Attribute)
            and receiver.attr == "ProviderRegistry"
        )

    if (
        isinstance(func, ast.Call)
        and isinstance(func.func, ast.Name)
        and func.func.id == "getattr"
        and len(func.args) >= 2
        and isinstance(func.args[1], ast.Constant)
        and func.args[1].value == "from_env"
    ):
        receiver = func.args[0]
        return (
            isinstance(receiver, ast.Name) and receiver.id in names
        ) or (
            isinstance(receiver, ast.Attribute)
            and receiver.attr == "ProviderRegistry"
        )

    return False


def _backend_local_provider_consumers() -> tuple[str, ...]:
    """Return production backend modules that still activate ProviderRegistry locally."""

    consumers: list[str] = []
    backend_root = ROOT / "backend"
    for path in sorted(backend_root.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if "/tests/" in "/" + relative:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError) as exc:
            check(False, f"cannot inspect backend provider consumer {relative}: {exc}")
            continue

        names = _provider_registry_names(tree)
        aliases = _provider_registry_activation_aliases(tree, names)
        if any(
            isinstance(node, ast.Call)
            and _is_provider_registry_from_env_call(node, names, aliases)
            for node in ast.walk(tree)
        ):
            consumers.append(relative)
    return tuple(consumers)

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
    check(
        "SKELETON_INTERNAL_URL=${SKELETON_INTERNAL_URL:-http://skeleton:8001}" in base,
        "backend internal Skeleton endpoint default drift",
    )

    skeleton_block = (
        base.split("  skeleton:", 1)[1].split("\n  backend:", 1)[0]
        if "  skeleton:" in base and "\n  backend:" in base
        else ""
    )
    backend_block = (
        base.split("  backend:", 1)[1].split("\n  frontend:", 1)[0]
        if "  backend:" in base and "\n  frontend:" in base
        else ""
    )
    engine_token_marker = (
        "SKL_ENGINE_SERVICE_TOKEN="
        "${SKL_ENGINE_SERVICE_TOKEN:?SKL_ENGINE_SERVICE_TOKEN must be set to a high-entropy value}"
    )
    check(
        engine_token_marker in skeleton_block,
        "Skeleton engine service authentication token binding missing",
    )
    check(
        engine_token_marker in backend_block,
        "backend engine service authentication token binding missing",
    )

    local_provider_consumers = _backend_local_provider_consumers()
    for provider_secret in ("OPENAI_API_KEY", "EMERGENT_LLM_KEY"):
        check(
            provider_secret + "=" in skeleton_block,
            f"Skeleton engine must receive runtime provider credential: {provider_secret}",
        )
        if local_provider_consumers:
            check(
                provider_secret + "=" in backend_block,
                (
                    "backend provider credential removed before local-provider parity: "
                    + provider_secret
                    + "; consumers="
                    + ",".join(local_provider_consumers)
                ),
            )
        else:
            check(
                provider_secret + "=" not in backend_block,
                f"backend retained runtime provider credential after cutover: {provider_secret}",
            )

    for durable_path in (
        "SKL_ENGINE_EXECUTION_STATE_PATH=/app/data/engine_execution.sqlite",
        "SKL_ENGINE_SUBMISSION_STATE_PATH=/app/data/engine_submissions.sqlite",
        "SKL_ENGINE_TOOL_RECEIPT_PATH=/app/data/engine_tool_receipts.sqlite",
    ):
        check(
            durable_path in skeleton_block,
            f"Skeleton engine durable state binding missing: {durable_path}",
        )

    check(
        "skeleton:\n        condition: service_healthy" in backend_block,
        "backend must wait for healthy Skeleton engine before AI ingress",
    )

    frontend_block = base.split("  frontend:", 1)[1].split("\n  mongo:", 1)[0] if "  frontend:" in base and "\n  mongo:" in base else ""
    check(
        "backend:\n        condition: service_healthy" in frontend_block,
        "frontend must wait for healthy backend",
    )
    check(
        "skeleton:\n        condition: service_healthy" in frontend_block,
        "frontend must wait for healthy Skeleton engine",
    )


def audit_production_ingress() -> None:
    nginx = read("frontend/nginx.conf")
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
    routed: list[tuple[str, str]] = []
    for name in ("backend", "skeleton"):
        service = services.get(name)
        check(isinstance(service, dict), f"ingress service missing from manifest: {name}")
        if not isinstance(service, dict):
            continue
        prefix = service.get("ingress_prefix")
        port = service.get("container_port")
        health_path = service.get("health_path")
        check(isinstance(prefix, str) and prefix.startswith("/"), f"manifest ingress prefix missing: {name}")
        check(isinstance(port, int), f"manifest container port missing: {name}")
        if not isinstance(prefix, str) or not prefix.startswith("/") or not isinstance(port, int):
            continue
        location = f"location ^~ {prefix.rstrip('/')}/ {{"
        upstream = f"proxy_pass http://{name}:{port};"
        check(location in nginx, f"production ingress missing manifest route: {location}")
        check(upstream in nginx, f"production ingress upstream drift: {upstream}")
        if isinstance(health_path, str) and health_path:
            check(
                prefix == "/" or health_path.startswith(prefix.rstrip("/") + "/"),
                f"{name} health path escapes ingress prefix: {health_path} vs {prefix}",
            )
        routed.append((prefix, location))

    if len(routed) >= 2:
        by_specificity = sorted(routed, key=lambda item: len(item[0]), reverse=True)
        positions = [nginx.find(location) for _, location in by_specificity]
        check(
            all(position >= 0 for position in positions) and positions == sorted(positions),
            "more-specific ingress prefixes must be declared before broader prefixes",
        )

    frontend = services.get("frontend")
    if isinstance(frontend, dict):
        check(frontend.get("ingress_prefix") == "/", "frontend must own the root ingress prefix")
        check("location / {" in nginx, "production frontend root ingress missing")

    registry = read("backend/core/routes_registry.py")
    server = read("backend/server.py")
    check("/api/v1" not in registry, "legacy backend route registry claims engine /api/v1")
    check("/api/v1" not in server, "legacy backend server claims engine /api/v1")

    engine_routes = read("skeleton/api/routes.py")
    check('payload["application"]' in engine_routes, "engine liveness canonical application identity missing")
    check('"component": "engine"' in engine_routes, "engine liveness component identity missing")
    check('_APP_MANIFEST.version' in engine_routes, "engine liveness version bypasses assembly manifest")


def audit_launcher_convergence() -> None:
    launch = read("frontend/components/LaunchCascade.tsx")
    boot = read("frontend/components/BootLauncher.tsx")
    stages = read("frontend/src/boot/stages.ts")
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
    check("id: 'assembly_contract'" in stages, "boot pipeline missing assembly contract stage")
    check("id: 'app_runtime'" in stages, "boot pipeline missing aggregate runtime stage")
    check("getAppBootstrap" in stages, "boot pipeline bypasses public bootstrap contract")
    check("getAppRuntimeStatus" in stages, "boot pipeline bypasses aggregate runtime status")
    check("finalSnapshot.stages.app_runtime" in boot, "warm boot cache bypasses aggregate runtime verdict")
    check("runtimeOk" in boot, "warm boot cache runtime health marker missing")


def _backend_product_policy() -> dict[str, tuple[str, ...]]:
    tree = ast.parse(read("backend/core/canonical_product_policy.py"))
    for node in tree.body:
        value = None
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "CANONICAL_PRODUCT_POLICY":
                value = node.value
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "CANONICAL_PRODUCT_POLICY" for target in node.targets):
                value = node.value
        if value is None:
            continue
        if not isinstance(value, ast.Tuple):
            break
        policy: dict[str, tuple[str, ...]] = {}
        for item in value.elts:
            check(
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "CanonicalDomainPolicy"
                and len(item.args) == 2,
                "canonical product policy contains unsupported syntax",
            )
            if not (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "CanonicalDomainPolicy"
                and len(item.args) == 2
            ):
                continue
            domain_node, actions_node = item.args
            if not (
                isinstance(domain_node, ast.Constant)
                and isinstance(domain_node.value, str)
                and isinstance(actions_node, ast.Tuple)
            ):
                FAILURES.append("canonical product policy must use literal domain/action tuples")
                continue
            actions: list[str] = []
            for action_node in actions_node.elts:
                if not isinstance(action_node, ast.Constant) or not isinstance(action_node.value, str):
                    FAILURES.append(f"canonical product policy action for {domain_node.value} is not a literal string")
                    continue
                actions.append(action_node.value)
            policy[domain_node.value] = tuple(actions)
        return policy
    FAILURES.append("CANONICAL_PRODUCT_POLICY assignment not found")
    return {}


def _backend_product_kernel() -> dict[str, tuple[str, ...]]:
    tree = ast.parse(read("backend/core/product_kernel.py"))
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != "CAPABILITIES":
            continue
        if not isinstance(node.value, ast.Tuple):
            break
        kernel: dict[str, tuple[str, ...]] = {}
        for item in node.value.elts:
            if not (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "Capability"
                and len(item.args) >= 4
                and isinstance(item.args[0], ast.Constant)
                and isinstance(item.args[0].value, str)
                and isinstance(item.args[3], ast.Tuple)
            ):
                FAILURES.append("product kernel capability contains unsupported syntax")
                continue
            prefixes: list[str] = []
            for prefix_node in item.args[3].elts:
                if isinstance(prefix_node, ast.Constant) and isinstance(prefix_node.value, str):
                    prefixes.append(prefix_node.value)
                else:
                    FAILURES.append(f"product kernel prefix for {item.args[0].value} is not a literal string")
            kernel[item.args[0].value] = tuple(prefixes)
        return kernel
    FAILURES.append("product kernel CAPABILITIES assignment not found")
    return {}


def _frontend_product_catalog() -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    source = read("frontend/src/product/productCatalog.ts")
    block_re = re.compile(
        r"(?ms)^  \{\n    id: '([^']+)'.*?^    backendSurface: '([^']+)',.*?^    actions: \[(.*?)^    \],\n^  \},"
    )
    policy: dict[str, tuple[str, ...]] = {}
    surfaces: dict[str, str] = {}
    for match in block_re.finditer(source):
        capability_id, surface, action_block = match.groups()
        actions = tuple(re.findall(r"operation: '([^']+)'", action_block))
        policy[capability_id] = actions
        surfaces[capability_id] = surface
    check(bool(policy), "frontend canonical product catalog could not be parsed")
    return policy, surfaces


def _backend_executor_bindings() -> tuple[set[tuple[str, str]], list[tuple[str, str]]]:
    tree = ast.parse(read("backend/core/product_default_executors.py"))
    ordered: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "register"
            and isinstance(func.value, ast.Name)
            and func.value.id == "registry"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            continue
        ordered.append((node.args[0].value, node.args[1].value))
    return set(ordered), ordered


def audit_product_catalog_alignment() -> None:
    backend_policy = _backend_product_policy()
    kernel = _backend_product_kernel()
    frontend_policy, frontend_surfaces = _frontend_product_catalog()

    check(
        set(frontend_policy) == set(backend_policy),
        f"frontend/backend product capability drift: frontend={sorted(frontend_policy)} backend={sorted(backend_policy)}",
    )
    check(
        set(kernel) == set(backend_policy),
        f"kernel/policy capability drift: kernel={sorted(kernel)} policy={sorted(backend_policy)}",
    )

    for capability_id, backend_actions in backend_policy.items():
        frontend_actions = frontend_policy.get(capability_id, ())
        check(
            frontend_actions == backend_actions,
            f"product action drift for {capability_id}: frontend={frontend_actions} backend={backend_actions}",
        )
        surface = frontend_surfaces.get(capability_id)
        prefixes = kernel.get(capability_id, ())
        check(
            surface in prefixes,
            f"frontend backendSurface for {capability_id} is not owned by product kernel: {surface!r} not in {prefixes}",
        )

    expected_bindings = {
        (domain, action)
        for domain, actions in backend_policy.items()
        for action in actions
    }
    executor_bindings, ordered_bindings = _backend_executor_bindings()
    check(
        executor_bindings == expected_bindings,
        f"canonical executor binding drift: bound={sorted(executor_bindings)} expected={sorted(expected_bindings)}",
    )
    check(
        len(ordered_bindings) == len(executor_bindings),
        "canonical executor bindings must not contain duplicate capability/action pairs",
    )


def audit_public_app_bootstrap_contract() -> None:
    bootstrap = read("skeleton/app/bootstrap.py")
    route = read("backend/routes/app_runtime.py")
    registry = read("backend/core/routes_registry.py")
    client = read("frontend/src/product/appBootstrapClient.ts")

    check("def public_bootstrap_payload(" in bootstrap, "public bootstrap payload builder missing")
    check('"health_path": service.health_path' in bootstrap, "bootstrap does not source health paths from manifest")
    check('"ingress_prefix": service.ingress_prefix' in bootstrap, "bootstrap does not source ingress prefixes from manifest")
    for forbidden in ("required_env", "optional_env", "public_url", "container_port", "entrypoint"):
        check(forbidden not in bootstrap, f"public bootstrap leaks internal field: {forbidden}")

    check(
        'APIRouter(prefix=_MANIFEST.public_contract["prefix"]' in route,
        "public app runtime router must use manifest prefix",
    )
    check(
        '@router.get(_MANIFEST.public_contract["bootstrap"])' in route,
        "public app bootstrap route must use manifest contract",
    )
    check(
        '@router.get(_MANIFEST.public_contract["status"])' in route,
        "aggregate app runtime status route must use manifest contract",
    )
    check(
        '@router.get(_MANIFEST.public_contract["ready"])' in route,
        "aggregate app readiness route must use manifest contract",
    )
    check("public_bootstrap_payload()" in route, "app bootstrap route bypasses canonical payload builder")
    check("asyncio.to_thread(_probe_engine" in route, "aggregate app status does not isolate engine probe")
    check('"identity mismatch"' in route, "aggregate app status does not validate engine identity")
    check('identity.get(key) == value' in route, "engine identity verification is incomplete")
    check("async def _probe_mongo" in route, "aggregate app status state probe missing")
    check('core_db.command("ping")' in route, "aggregate app status does not verify durable state")
    check("asyncio.gather(" in route, "aggregate app status probes are not concurrent")
    check("public_readiness()" in route, "aggregate app status omits product readiness")
    check('"product": product_readiness' in route, "aggregate app status product summary missing")
    check("SKELETON_INTERNAL_URL" in route, "aggregate app status internal engine endpoint missing")
    check('("routes.app_runtime",' in registry, "public app runtime router is not registered")

    check("getAppBootstrap" in client, "frontend app bootstrap client missing")
    check("DEFAULT_APP_BOOTSTRAP_PATH = '/api/app/bootstrap'" in client, "frontend bootstrap seed endpoint drift")
    check("getAppRuntimeStatus" in client, "frontend aggregate app runtime client missing")
    check("bootstrap?.contract.status || DEFAULT_APP_STATUS_PATH" in client, "frontend runtime path bypasses bootstrap contract")
    check("bootstrapService" in client, "frontend app bootstrap service resolver missing")


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
    check("getAppBootstrap" in client, "product health no longer consumes canonical app bootstrap")
    check("getAppRuntimeStatus" in client, "product health bypasses aggregate app runtime status")
    check("bootstrapService" in client, "product health bypasses bootstrap service metadata")
    check(
        "contractSource: 'runtime' | 'bootstrap-fallback' | 'static-fallback'" in client,
        "health contract provenance missing",
    )
    check(
        "ok: false," in client and "whole-application verdict remains fail-closed" in client,
        "direct health fallback must not claim whole-app readiness",
    )

    for name in ("backend", "skeleton"):
        service = services.get(name)
        check(isinstance(service, dict), f"manifest health service missing: {name}")
        if not isinstance(service, dict):
            continue
        path = service.get("health_path")
        check(isinstance(path, str) and bool(path), f"manifest health path missing: {name}")
        if isinstance(path, str) and path:
            fallback_token = f"{name}: {path!r}"
            check(
                fallback_token in client,
                f"health fallback drift for {name}: expected {path}",
            )

    check("probeAppHealth" in shell, "product shell no longer probes whole-app health")
    check("Application runtime" in shell, "product shell runtime health panel missing")
    check("health.contractSource" in shell, "product shell does not surface bootstrap/fallback provenance")
    check("health.application.name" in shell, "product shell does not surface canonical application identity")


def audit_public_product_readiness_contract() -> None:
    route = read("backend/routes/product_runtime.py")
    runtime = read("backend/core/product_control_runtime.py")
    registry = read("backend/core/routes_registry.py")
    client = read("frontend/src/product/productControlClient.ts")
    capability = read("frontend/app/capability.tsx")
    product = read("frontend/app/product.tsx")

    check('APIRouter(prefix="/api/product"' in route, "public product router prefix drift")
    check('@router.get("/readiness")' in route, "public product readiness route missing")
    check("public_readiness()" in route, "public readiness route bypasses sanitized projection")
    check('("routes.product_runtime",' in registry, "public product router is not registered")
    check("def public_readiness(" in runtime, "sanitized product readiness projection missing")
    check("const PUBLIC_ROOT = '/api/product';" in client, "frontend public product client root drift")
    check("getProductReadiness" in capability, "capability UI bypasses public readiness client")
    check("getProductReadiness" not in product, "product shell still duplicates readiness request")
    check("health?.product?.available" in product, "product shell does not consume runtime product summary")


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
    audit_topology_alignment()
    audit_backend_public_identity()
    audit_no_competing_root_launchers()
    audit_endpoint_boundary()
    audit_compose_modes()
    audit_production_ingress()
    audit_launcher_convergence()
    audit_product_catalog_alignment()
    audit_public_app_bootstrap_contract()
    audit_product_health_contract()
    audit_public_product_readiness_contract()
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
