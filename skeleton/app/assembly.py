"""Repository-wide application assembly primitives.

The repository contains a browser-facing Expo application, a legacy FastAPI
application API, the Skeleton v16 engine API, and data services.  This module
defines the stable boundary that treats those components as one deployable
application without erasing their internal ownership boundaries.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ServiceSpec:
    """One process or backing service in the assembled application."""

    name: str
    role: str
    path: str
    kind: str
    depends_on: tuple[str, ...] = ()
    public_url: str = ""
    health_path: str = ""
    ingress_prefix: str = ""
    entrypoint: str = ""
    container_port: int | None = None
    canonical: bool = True
    profile: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ServiceSpec":
        name = str(value.get("name", "")).strip()
        role = str(value.get("role", "")).strip()
        path = str(value.get("path", "")).strip()
        kind = str(value.get("kind", "")).strip()
        if not all((name, role, path, kind)):
            raise ValueError("service requires non-empty name, role, path and kind")
        raw_deps = value.get("depends_on", ())
        if not isinstance(raw_deps, list):
            raise ValueError(f"service {name!r} depends_on must be a list")
        port = value.get("container_port")
        return cls(
            name=name,
            role=role,
            path=path,
            kind=kind,
            depends_on=tuple(str(item) for item in raw_deps),
            public_url=str(value.get("public_url", "") or ""),
            health_path=str(value.get("health_path", "") or ""),
            ingress_prefix=str(value.get("ingress_prefix", "") or ""),
            entrypoint=str(value.get("entrypoint", "") or ""),
            container_port=int(port) if port is not None else None,
            canonical=bool(value.get("canonical", True)),
            profile=str(value.get("profile", "") or ""),
        )


@dataclass(frozen=True)
class AssemblyManifest:
    """Validated application topology loaded from the packaged manifest."""

    schema_version: int
    name: str
    version: str
    compose_file: str
    hot_compose_file: str
    public_contract: dict[str, str]
    modes: dict[str, dict[str, str]]
    default_services: tuple[str, ...]
    full_services: tuple[str, ...]
    required_env: tuple[str, ...]
    optional_env: tuple[str, ...]
    required_paths: tuple[str, ...]
    services: tuple[ServiceSpec, ...]
    architecture: dict[str, str] = field(default_factory=dict)
    construction: dict[str, str] = field(default_factory=dict)

    @property
    def service_names(self) -> tuple[str, ...]:
        return tuple(service.name for service in self.services)

    def service(self, name: str) -> ServiceSpec:
        for service in self.services:
            if service.name == name:
                return service
        raise KeyError(name)

    def mode_env(self, name: str) -> dict[str, str]:
        try:
            return dict(self.modes[name])
        except KeyError as exc:
            raise KeyError(f"unknown application mode: {name}") from exc

    def contract_path(self, name: str) -> str:
        try:
            suffix = self.public_contract[name]
            prefix = self.public_contract["prefix"]
        except KeyError as exc:
            raise KeyError(f"unknown public application contract route: {name}") from exc
        return prefix.rstrip("/") + "/" + suffix.lstrip("/")


@dataclass(frozen=True)
class AssemblyCheck:
    """One deterministic preflight result."""

    code: str
    ok: bool
    message: str
    required: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "ok": self.ok,
            "message": self.message,
            "required": self.required,
        }


def _manifest_bytes() -> bytes:
    return resources.files("skeleton.app").joinpath("manifest.json").read_bytes()


def parse_manifest(payload: Mapping[str, object]) -> AssemblyManifest:
    """Validate a decoded application manifest payload."""

    if payload.get("schema_version") != 1:
        raise ValueError("unsupported application assembly manifest schema")

    app = payload.get("app")
    runtime = payload.get("runtime")
    architecture = payload.get("architecture")
    construction = payload.get("construction")
    if not isinstance(app, dict) or not isinstance(runtime, dict):
        raise ValueError("manifest requires app and runtime objects")
    if not isinstance(architecture, dict) or not architecture:
        raise ValueError("manifest requires architecture contract metadata")
    if not isinstance(construction, dict) or not construction:
        raise ValueError("manifest requires AI construction contract metadata")

    def _string_map(name: str, value: dict[str, object]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or not isinstance(item, str) or not item:
                raise ValueError(f"{name} metadata must contain non-empty string values")
            result[key] = item
        return result

    architecture_metadata = _string_map("architecture", architecture)
    construction_metadata = _string_map("construction", construction)

    raw_services = payload.get("services")
    if not isinstance(raw_services, list) or not raw_services:
        raise ValueError("manifest requires at least one service")
    if not all(isinstance(item, Mapping) for item in raw_services):
        raise ValueError("manifest services must contain objects")
    services = tuple(ServiceSpec.from_mapping(item) for item in raw_services)
    names = tuple(service.name for service in services)
    if len(set(names)) != len(names):
        raise ValueError("service names must be unique")

    app_name = app.get("name")
    app_version = app.get("version")
    if not isinstance(app_name, str) or not app_name.strip():
        raise ValueError("app name must be a non-empty string")
    if not isinstance(app_version, str) or not app_version.strip():
        raise ValueError("app version must be a non-empty string")

    raw_contract = app.get("public_contract")
    if not isinstance(raw_contract, dict):
        raise ValueError("app public_contract must be an object")
    required_contract_keys = ("prefix", "bootstrap", "status", "ready")
    public_contract: dict[str, str] = {}
    for key in required_contract_keys:
        value = raw_contract.get(key)
        if not isinstance(value, str) or not value.startswith("/"):
            raise ValueError(f"public_contract {key!r} must be an absolute path fragment")
        if value != "/" and value.endswith("/"):
            raise ValueError(f"public_contract {key!r} must not end with '/'")
        public_contract[key] = value
    if len({public_contract[key] for key in ("bootstrap", "status", "ready")}) != 3:
        raise ValueError("public_contract routes must be unique")

    raw_modes = app.get("modes", {"development": {}})
    if not isinstance(raw_modes, dict) or not raw_modes:
        raise ValueError("app modes must be a non-empty object")
    modes: dict[str, dict[str, str]] = {}
    for mode_name, raw_mode in raw_modes.items():
        if not isinstance(mode_name, str) or not mode_name.strip():
            raise ValueError("app mode names must be non-empty strings")
        if not isinstance(raw_mode, dict):
            raise ValueError(f"app mode {mode_name!r} must be an object")
        mode_env: dict[str, str] = {}
        for key, value in raw_mode.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(value, str):
                raise ValueError(f"app mode {mode_name!r} must contain string env values")
            mode_env[key] = value
        modes[mode_name] = mode_env
    if "development" not in modes or "production" not in modes:
        raise ValueError("app modes must define development and production")

    default_services = tuple(str(item) for item in app.get("default_services", ()))
    full_services = tuple(str(item) for item in app.get("full_services", ()))
    unknown = (set(default_services) | set(full_services)) - set(names)
    if unknown:
        raise ValueError(f"manifest references unknown services: {sorted(unknown)}")
    if not default_services:
        raise ValueError("default_services must not be empty")
    if not full_services:
        raise ValueError("full_services must not be empty")
    if not set(default_services).issubset(set(full_services)):
        raise ValueError("full_services must contain every default service")

    ingress_prefixes: dict[str, str] = {}
    for service in services:
        missing = set(service.depends_on) - set(names)
        if missing:
            raise ValueError(
                f"service {service.name!r} depends on unknown services: {sorted(missing)}"
            )

        if service.name in service.depends_on:
            raise ValueError(f"service {service.name!r} cannot depend on itself")
        if service.health_path and not service.health_path.startswith("/"):
            raise ValueError(f"service {service.name!r} health_path must start with '/'")

        prefix = service.ingress_prefix
        if prefix:
            if not prefix.startswith("/"):
                raise ValueError(f"service {service.name!r} ingress_prefix must start with '/'")
            if prefix != "/" and prefix.endswith("/"):
                raise ValueError(f"service {service.name!r} ingress_prefix must not end with '/'")
            owner = ingress_prefixes.get(prefix)
            if owner is not None:
                raise ValueError(
                    f"ingress_prefix {prefix!r} is shared by {owner!r} and {service.name!r}"
                )
            ingress_prefixes[prefix] = service.name
            if service.health_path and prefix != "/" and not service.health_path.startswith(prefix + "/"):
                raise ValueError(
                    f"service {service.name!r} health_path must live under ingress_prefix {prefix!r}"
                )

    backend = next((service for service in services if service.name == "backend"), None)
    if backend is None:
        raise ValueError("manifest requires canonical backend service")
    contract_prefix = public_contract["prefix"]
    backend_prefix = backend.ingress_prefix
    if not backend_prefix or (
        contract_prefix != backend_prefix
        and not contract_prefix.startswith(backend_prefix.rstrip("/") + "/")
    ):
        raise ValueError(
            "public application contract must live inside backend ingress prefix"
        )

    required_paths = payload.get("required_paths", ())
    if not isinstance(required_paths, list):
        raise ValueError("required_paths must be a list")

    required_env = runtime.get("required_env", ())
    optional_env = runtime.get("optional_env", ())
    if not isinstance(required_env, list) or not isinstance(optional_env, list):
        raise ValueError("runtime env declarations must be lists")

    return AssemblyManifest(
        schema_version=1,
        name=app_name.strip(),
        version=app_version.strip(),
        compose_file=str(app.get("compose_file", "docker-compose.yml")),
        hot_compose_file=str(app.get("hot_compose_file", "docker-compose.hot.yml")),
        public_contract=public_contract,
        modes=modes,
        default_services=default_services,
        full_services=full_services,
        required_env=tuple(str(item) for item in required_env),
        optional_env=tuple(str(item) for item in optional_env),
        required_paths=tuple(str(item) for item in required_paths),
        services=services,
        architecture=architecture_metadata,
        construction=construction_metadata,
    )



def load_manifest() -> AssemblyManifest:
    """Load and validate the packaged application assembly manifest."""

    payload = json.loads(_manifest_bytes().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("application assembly manifest root must be an object")
    return parse_manifest(payload)

def find_repo_root(start: Path | None = None) -> Path:
    """Find the checkout root without depending on the current working directory."""

    cursor = (start or Path.cwd()).resolve()
    if cursor.is_file():
        cursor = cursor.parent
    for candidate in (cursor, *cursor.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "docker-compose.yml"
        ).is_file():
            return candidate
    raise FileNotFoundError("could not locate Skeleton repository root")


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _runtime_env(root: Path, environ: Mapping[str, str] | None) -> dict[str, str]:
    values = _read_dotenv(root / ".env")
    source = os.environ if environ is None else environ
    values.update({str(key): str(value) for key, value in source.items()})
    return values


def _usable_secret(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    placeholders = (
        "change-me",
        "changeme",
        "your-key-here",
        "your-secret",
        "replace-me",
        "example",
    )
    return not any(token in lowered for token in placeholders)


def preflight(
    root: Path | None = None,
    *,
    runtime: bool = False,
    environ: Mapping[str, str] | None = None,
    manifest: AssemblyManifest | None = None,
) -> tuple[AssemblyCheck, ...]:
    """Validate repository structure and, optionally, runtime prerequisites."""

    manifest = manifest or load_manifest()
    root = root or find_repo_root()
    checks: list[AssemblyCheck] = []

    for relative in manifest.required_paths:
        path = root / relative
        checks.append(
            AssemblyCheck(
                code=f"path:{relative}",
                ok=path.exists(),
                message=(
                    f"required path present: {relative}"
                    if path.exists()
                    else f"missing required path: {relative}"
                ),
            )
        )

    for service in manifest.services:
        path = root / service.path
        checks.append(
            AssemblyCheck(
                code=f"service:{service.name}:path",
                ok=path.exists(),
                message=(
                    f"{service.name} source boundary present at {service.path}"
                    if path.exists()
                    else f"{service.name} source boundary missing at {service.path}"
                ),
            )
        )

    try:
        from skeleton.app.plan import validate_manifest_topology

        default_plan, full_plan = validate_manifest_topology(manifest)
    except ValueError as exc:
        checks.append(
            AssemblyCheck(
                code="topology:graph",
                ok=False,
                message=f"application topology invalid: {exc}",
            )
        )
    else:
        checks.append(
            AssemblyCheck(
                code="topology:graph",
                ok=True,
                message=(
                    "application topology valid: "
                    f"default={len(default_plan.services)} services, "
                    f"full={len(full_plan.services)} services"
                ),
            )
        )

    if runtime:
        docker = shutil.which("docker")
        checks.append(
            AssemblyCheck(
                code="runtime:docker",
                ok=docker is not None,
                message=(
                    f"docker available at {docker}" if docker else "docker executable not found"
                ),
            )
        )
        values = _runtime_env(root, environ)
        for key in manifest.required_env:
            ok = _usable_secret(values.get(key, ""))
            checks.append(
                AssemblyCheck(
                    code=f"env:{key}",
                    ok=ok,
                    message=(
                        f"runtime value configured: {key}"
                        if ok
                        else f"runtime value missing or placeholder: {key}"
                    ),
                )
            )

    return tuple(checks)


def checks_ok(checks: Iterable[AssemblyCheck]) -> bool:
    return all(check.ok or not check.required for check in checks)


def compose_command(
    action: str,
    *,
    manifest: AssemblyManifest | None = None,
    full: bool = False,
    build: bool = True,
    follow: bool = False,
    service: str = "",
    hot: bool = False,
) -> tuple[str, ...]:
    """Build a shell-free Docker Compose command for the unified app."""

    manifest = manifest or load_manifest()
    action = action.strip().lower()
    base = ["docker", "compose", "-f", manifest.compose_file]
    if hot:
        base.extend(["-f", manifest.hot_compose_file])

    if action == "up":
        from skeleton.app.plan import build_plan

        plan = build_plan(manifest=manifest, full=full)
        profiles: list[str] = []
        for service_name in plan.services:
            profile = manifest.service(service_name).profile
            if profile and profile not in profiles:
                profiles.append(profile)
        for profile in profiles:
            base.extend(["--profile", profile])
        command = [*base, "up", "-d"]
        if build:
            command.append("--build")
        command.extend(plan.services)
        return tuple(command)
    if action == "down":
        return tuple([*base, "down", "--remove-orphans"])
    if action == "ps":
        return tuple([*base, "ps"])
    if action == "logs":
        command = [*base, "logs"]
        if follow:
            command.append("--follow")
        if service:
            if service not in manifest.service_names:
                raise ValueError(f"unknown service: {service}")
            command.append(service)
        return tuple(command)
    if action == "config":
        return tuple([*base, "config"])

    raise ValueError(f"unsupported compose action: {action}")


def manifest_payload(manifest: AssemblyManifest | None = None) -> dict[str, object]:
    """Return a stable machine-readable topology snapshot."""

    manifest = manifest or load_manifest()
    return {
        "schema_version": manifest.schema_version,
        "name": manifest.name,
        "version": manifest.version,
        "compose_file": manifest.compose_file,
        "hot_compose_file": manifest.hot_compose_file,
        "public_contract": dict(manifest.public_contract),
        "modes": {name: dict(values) for name, values in manifest.modes.items()},
        "default_services": list(manifest.default_services),
        "full_services": list(manifest.full_services),
        "required_env": list(manifest.required_env),
        "architecture": dict(manifest.architecture),
        "construction": dict(manifest.construction),
        "services": [
            {
                "name": service.name,
                "role": service.role,
                "kind": service.kind,
                "path": service.path,
                "entrypoint": service.entrypoint,
                "public_url": service.public_url,
                "health_path": service.health_path,
                "ingress_prefix": service.ingress_prefix,
                "container_port": service.container_port,
                "depends_on": list(service.depends_on),
                "canonical": service.canonical,
                "profile": service.profile,
            }
            for service in manifest.services
        ],
    }
