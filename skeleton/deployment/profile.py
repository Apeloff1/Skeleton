"""Self-host deployment profiles.

A :class:`SelfHostProfile` is the single, declarative description of how one
Skeleton instance is hosted: bind address, durable state layout, optional
external services, observability and the engine service boundary.

Profiles are pure data. They render to the exact ``SKL_*`` environment the
runtime already consumes (:mod:`skeleton.config.settings`, the governance
bindings in :mod:`skeleton.api.server` and the ``docker-compose.yml`` service
definition), and they parse back from such an environment, so a profile, an
``.env`` file and a container environment are interchangeable views of the
same configuration.

This module is stdlib-only and import-light on purpose: the deploy CLI must
be able to describe and validate a host before any runtime dependency is
importable.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

__all__ = [
    "ENVIRONMENTS",
    "LOG_LEVELS",
    "MEMORY_PATH",
    "PROVIDER_KEY_ENV",
    "STORE_LAYOUT",
    "ProfileError",
    "Secret",
    "SelfHostProfile",
    "builtin_profile_names",
    "get_profile",
    "list_profiles",
    "parse_bool",
    "parse_csv",
    "register_profile",
    "resolve_profile",
]

ENVIRONMENTS: Tuple[str, ...] = ("development", "staging", "production", "test")
LOG_LEVELS: Tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
MEMORY_PATH = ":memory:"

#: Durable stores: (profile key, environment variable, file name under data_dir).
#: File names match the ``skeleton`` service in ``docker-compose.yml``.
STORE_LAYOUT: Tuple[Tuple[str, str, str], ...] = (
    ("operation_state", "SKL_OPERATION_STATE_PATH", "operation_state.sqlite"),
    ("operation_stream", "SKL_OPERATION_STREAM_PATH", "operation_stream.sqlite"),
    ("engine_execution", "SKL_ENGINE_EXECUTION_STATE_PATH", "engine_execution.sqlite"),
    ("engine_submission", "SKL_ENGINE_SUBMISSION_STATE_PATH", "engine_submissions.sqlite"),
    ("engine_tool_receipt", "SKL_ENGINE_TOOL_RECEIPT_PATH", "engine_tool_receipts.sqlite"),
    ("engine_quota", "SKL_ENGINE_QUOTA_STATE_PATH", "engine_quota.sqlite"),
    ("engine_pressure", "SKL_ENGINE_PRESSURE_STATE_PATH", "engine_pressure.sqlite"),
    ("governance_lifecycle", "SKL_GOVERNANCE_LIFECYCLE_PATH", "governance_lifecycle.sqlite"),
)
STORE_KEYS: Tuple[str, ...] = tuple(key for key, _env, _name in STORE_LAYOUT)
_STORE_ENV: Dict[str, str] = {key: env for key, env, _name in STORE_LAYOUT}
_ENV_STORE: Dict[str, str] = {env: key for key, env, _name in STORE_LAYOUT}

#: Outbound model-provider credentials stripped from the child environment of
#: an ``offline`` profile so a self-hosted instance cannot reach a provider.
PROVIDER_KEY_ENV: Tuple[str, ...] = (
    "OPENAI_API_KEY",
    "EMERGENT_LLM_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "XAI_API_KEY",
    "SKL_JEEVES_API_KEY",
)

# Scalar environment bindings: env var -> (profile field, kind).
_SCALAR_ENV: Tuple[Tuple[str, str, str], ...] = (
    ("SKL_ENVIRONMENT", "environment", "str"),
    ("SKL_SERVER_HOST", "host", "str"),
    ("SKL_SERVER_PORT", "port", "int"),
    ("SKL_MONGO_URI", "mongo_uri", "str"),
    ("SKL_MONGO_DATABASE", "mongo_database", "str"),
    ("SKL_CHROMA_HOST", "chroma_host", "str"),
    ("SKL_CHROMA_PORT", "chroma_port", "int"),
    ("SKL_CHROMA_COLLECTION", "chroma_collection", "str"),
    ("SKL_OBS_LOG_LEVEL", "log_level", "str"),
    ("SKL_OBS_METRICS_ENABLED", "metrics_enabled", "bool"),
    ("SKL_OBS_TRACING_ENABLED", "tracing_enabled", "bool"),
    ("SKL_ENGINE_SERVICE_PRINCIPAL", "service_principal", "str"),
    ("SKL_ENGINE_ALLOWED_TENANTS_CSV", "allowed_tenants", "csv"),
    ("SKL_ENGINE_ALLOWED_CAPABILITIES_CSV", "allowed_capabilities", "csv"),
    ("SKELETON_PUBLIC_DEV_SURFACES", "public_dev_surfaces", "bool"),
)
TOKEN_ENV = "SKL_ENGINE_SERVICE_TOKEN"
CHROMA_PERSIST_ENV = "SKL_CHROMA_PERSIST_DIRECTORY"
DATA_DIR_ENV = "SKELETON_DATA_DIR"
OFFLINE_ENV = "SKELETON_OFFLINE"
PROFILE_ENV = "SKELETON_DEPLOY_PROFILE"

#: Every variable a profile owns. ``extra_env`` may not shadow these.
MANAGED_ENV: frozenset = frozenset(
    [env for env, _f, _k in _SCALAR_ENV]
    + list(_STORE_ENV.values())
    + [TOKEN_ENV, CHROMA_PERSIST_ENV, DATA_DIR_ENV, OFFLINE_ENV, PROFILE_ENV]
)

_TRUE = frozenset({"1", "true", "yes", "on", "y", "t"})
_FALSE = frozenset({"0", "false", "no", "off", "n", "f", ""})


class ProfileError(ValueError):
    """Raised when a profile cannot be constructed or resolved."""


def parse_bool(value: Any) -> bool:
    """Parse the boolean spellings accepted by pydantic-settings."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ProfileError(f"not a boolean: {value!r}")


def parse_int(value: Any, *, name: str = "value") -> int:
    if isinstance(value, bool):
        raise ProfileError(f"{name} must be an integer, not a boolean")
    if isinstance(value, int):
        return value
    text = str(value).strip()
    try:
        return int(text, 10)
    except ValueError as exc:
        raise ProfileError(f"{name} must be an integer: {value!r}") from exc


def parse_csv(value: Any) -> Tuple[str, ...]:
    """Parse a CSV allow-list into a de-duplicated, order-preserving tuple."""

    if isinstance(value, (list, tuple)):
        items: Iterable[str] = (str(item) for item in value)
    else:
        items = str(value).split(",")
    out: list[str] = []
    for item in items:
        token = item.strip()
        if token and token not in out:
            out.append(token)
    return tuple(out)


class Secret:
    """A string whose value never appears in ``repr``/``str`` or JSON views."""

    __slots__ = ("_value",)

    def __init__(self, value: str = "") -> None:
        if isinstance(value, Secret):
            value = value.reveal()
        if not isinstance(value, str):
            raise ProfileError("secret values must be text")
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Secret):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Secret", self._value))

    def masked(self) -> str:
        return "**********" if self._value else ""

    def __repr__(self) -> str:
        return f"Secret({self.masked()!r})"

    __str__ = masked


def _coerce_secret(value: Any) -> Secret:
    if isinstance(value, Secret):
        return value
    if value is None:
        return Secret("")
    return Secret(str(value))


@dataclass(frozen=True)
class SelfHostProfile:
    """Declarative description of one self-hosted Skeleton instance."""

    name: str
    description: str = ""
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8001
    data_dir: Optional[str] = None
    mongo_uri: str = ""
    mongo_database: str = "skeleton"
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "skeleton_memory"
    chroma_persist: bool = False
    log_level: str = "INFO"
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    service_principal: str = "codedock-backend"
    service_token: Secret = field(default_factory=Secret)
    allowed_tenants: Tuple[str, ...] = ("*",)
    allowed_capabilities: Tuple[str, ...] = ("*",)
    public_dev_surfaces: bool = False
    offline: bool = False
    workers: int = 1
    store_overrides: Tuple[Tuple[str, str], ...] = ()
    extra_env: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "service_token", _coerce_secret(self.service_token))
        object.__setattr__(self, "allowed_tenants", parse_csv(self.allowed_tenants))
        object.__setattr__(self, "allowed_capabilities", parse_csv(self.allowed_capabilities))
        object.__setattr__(self, "environment", str(self.environment).strip().lower())
        object.__setattr__(self, "log_level", str(self.log_level).strip().upper())
        if not str(self.name).strip():
            raise ProfileError("profile name must not be empty")
        overrides = self.store_overrides
        if isinstance(overrides, Mapping):
            overrides = tuple(overrides.items())
        normalized_overrides: list[Tuple[str, str]] = []
        for key, value in overrides:
            if key not in _STORE_ENV:
                raise ProfileError(f"unknown store {key!r}; expected one of {', '.join(STORE_KEYS)}")
            normalized_overrides.append((key, str(value)))
        object.__setattr__(self, "store_overrides", tuple(sorted(normalized_overrides)))
        extra = self.extra_env
        if isinstance(extra, Mapping):
            extra = tuple(extra.items())
        object.__setattr__(self, "extra_env", tuple(sorted((str(k), str(v)) for k, v in extra)))
        if self.data_dir is not None:
            text = str(self.data_dir).strip()
            object.__setattr__(self, "data_dir", text or None)

    # ------------------------------------------------------------------ views
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def durable(self) -> bool:
        """True when every store is backed by a file rather than memory."""

        return all(path != MEMORY_PATH for path in self.store_paths().values())

    @property
    def base_url(self) -> str:
        host = self.host
        if host in ("0.0.0.0", "", "::"):
            host = "127.0.0.1"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}"

    def data_path(self) -> Optional[Path]:
        if self.data_dir is None:
            return None
        return Path(os.path.expanduser(self.data_dir))

    def store_paths(self) -> Dict[str, str]:
        """Return the store key -> path mapping (``:memory:`` without a data dir)."""

        overrides = dict(self.store_overrides)
        root = self.data_path()
        out: Dict[str, str] = {}
        for key, _env, filename in STORE_LAYOUT:
            if key in overrides:
                out[key] = overrides[key]
            elif root is None:
                out[key] = MEMORY_PATH
            else:
                out[key] = str(root / filename)
        return out

    def chroma_persist_directory(self) -> Optional[str]:
        if not self.chroma_persist:
            return None
        root = self.data_path()
        if root is None:
            return None
        return str(root / "chroma")

    def to_env(self, *, include_secrets: bool = True) -> Dict[str, str]:
        """Render the runtime environment for this profile (stable order)."""

        env: Dict[str, str] = {
            PROFILE_ENV: self.name,
            "SKL_ENVIRONMENT": self.environment,
            "SKL_SERVER_HOST": self.host,
            "SKL_SERVER_PORT": str(self.port),
        }
        if self.mongo_uri:
            env["SKL_MONGO_URI"] = self.mongo_uri
        env["SKL_MONGO_DATABASE"] = self.mongo_database
        env["SKL_CHROMA_HOST"] = self.chroma_host
        env["SKL_CHROMA_PORT"] = str(self.chroma_port)
        env["SKL_CHROMA_COLLECTION"] = self.chroma_collection
        persist = self.chroma_persist_directory()
        if persist:
            env[CHROMA_PERSIST_ENV] = persist
        env["SKL_OBS_LOG_LEVEL"] = self.log_level
        env["SKL_OBS_METRICS_ENABLED"] = "true" if self.metrics_enabled else "false"
        env["SKL_OBS_TRACING_ENABLED"] = "true" if self.tracing_enabled else "false"
        # Always emitted ("" = in-memory) so an env file fully determines the layout.
        env[DATA_DIR_ENV] = "" if self.data_dir is None else str(self.data_path())
        for key, path in self.store_paths().items():
            env[_STORE_ENV[key]] = path
        env["SKL_ENGINE_SERVICE_PRINCIPAL"] = self.service_principal
        if self.service_token:
            env[TOKEN_ENV] = self.service_token.reveal() if include_secrets else self.service_token.masked()
        env["SKL_ENGINE_ALLOWED_TENANTS_CSV"] = ",".join(self.allowed_tenants)
        env["SKL_ENGINE_ALLOWED_CAPABILITIES_CSV"] = ",".join(self.allowed_capabilities)
        if self.public_dev_surfaces:
            env["SKELETON_PUBLIC_DEV_SURFACES"] = "1"
        if self.offline:
            env[OFFLINE_ENV] = "1"
        for key, value in self.extra_env:
            env[key] = value
        return env

    def to_dict(self, *, redact: bool = True) -> Dict[str, Any]:
        """JSON-safe description; the service token is masked unless ``redact=False``."""

        out: Dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, Secret):
                value = value.masked() if redact else value.reveal()
            elif item.name in ("store_overrides", "extra_env"):
                value = dict(value)
            elif isinstance(value, tuple):
                value = list(value)
            out[item.name] = value
        out["store_paths"] = self.store_paths()
        out["durable"] = self.durable
        out["base_url"] = self.base_url
        return out

    def fingerprint(self) -> str:
        """Stable digest of the effective configuration (secret values excluded)."""

        payload = self.to_dict(redact=True)
        payload["service_token"] = {"set": bool(self.service_token), "length": len(self.service_token)}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def absolutized(self, base: Optional[str] = None) -> "SelfHostProfile":
        """Anchor a relative ``data_dir`` / store override at ``base`` (default: cwd).

        The boot path calls this before launching so the server process sees
        the same absolute paths that were validated, whatever its own cwd.
        """

        anchor = Path(base) if base else Path.cwd()
        changes: Dict[str, Any] = {}
        root = self.data_path()
        if root is not None and not root.is_absolute():
            changes["data_dir"] = str(anchor / root)
        stores = []
        for key, value in self.store_overrides:
            path = Path(os.path.expanduser(value))
            if value != MEMORY_PATH and not path.is_absolute():
                value = str(anchor / path)
            stores.append((key, value))
        if tuple(stores) != self.store_overrides:
            changes["store_overrides"] = tuple(stores)
        return replace(self, **changes) if changes else self

    # ------------------------------------------------------------- builders
    def with_overrides(self, **changes: Any) -> "SelfHostProfile":
        """Return a copy with ``changes`` applied (values are coerced)."""

        known = {item.name for item in fields(self)}
        unknown = sorted(set(changes) - known)
        if unknown:
            raise ProfileError(f"unknown profile field(s): {', '.join(unknown)}")
        coerced = {key: _coerce_field(key, value) for key, value in changes.items()}
        return replace(self, **coerced)

    def with_settings(self, assignments: Iterable[str]) -> "SelfHostProfile":
        """Apply ``key=value`` assignments (CLI ``--set``)."""

        changes: Dict[str, Any] = {}
        stores: Dict[str, str] = dict(self.store_overrides)
        for raw in assignments:
            if "=" not in raw:
                raise ProfileError(f"expected key=value, got {raw!r}")
            key, value = raw.split("=", 1)
            key = key.strip()
            if key.startswith("store."):
                stores[key[len("store."):]] = value
                continue
            changes[key] = value
        if stores != dict(self.store_overrides):
            changes["store_overrides"] = tuple(stores.items())
        return self.with_overrides(**changes) if changes else self

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SelfHostProfile":
        """Build a profile from a JSON-style mapping (e.g. a profile file)."""

        if not isinstance(data, Mapping):
            raise ProfileError("profile document must be a mapping")
        known = {item.name for item in fields(cls)}
        derived = {"store_paths", "durable", "base_url"}
        unknown = sorted(set(data) - known - derived)
        if unknown:
            raise ProfileError(f"unknown profile field(s): {', '.join(unknown)}")
        if "name" not in data:
            raise ProfileError("profile document requires a name")
        kwargs = {key: _coerce_field(key, value) for key, value in data.items() if key in known}
        return cls(**kwargs)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str],
        *,
        base: Optional["SelfHostProfile"] = None,
    ) -> "SelfHostProfile":
        """Overlay an ``SKL_*`` environment onto ``base`` (or a blank profile)."""

        profile = base if base is not None else cls(name=str(env.get(PROFILE_ENV) or "custom"))
        changes: Dict[str, Any] = {}
        for env_name, field_name, _kind in _SCALAR_ENV:
            if env_name in env:
                changes[field_name] = env[env_name]
        if TOKEN_ENV in env:
            changes["service_token"] = env[TOKEN_ENV]
        if DATA_DIR_ENV in env:
            changes["data_dir"] = env[DATA_DIR_ENV] or None
        if OFFLINE_ENV in env:
            changes["offline"] = env[OFFLINE_ENV]
        if CHROMA_PERSIST_ENV in env:
            changes["chroma_persist"] = bool(env[CHROMA_PERSIST_ENV].strip())
        candidate = profile.with_overrides(**changes) if changes else profile
        defaults = candidate.store_paths()
        stores = dict(candidate.store_overrides)
        for env_name, key in _ENV_STORE.items():
            if env_name in env:
                value = env[env_name]
                if value != defaults[key] or key in stores:
                    stores[key] = value
        if stores != dict(candidate.store_overrides):
            candidate = replace(candidate, store_overrides=tuple(stores.items()))
        return candidate


def _coerce_field(name: str, value: Any) -> Any:
    if name in ("port", "chroma_port", "workers"):
        return parse_int(value, name=name)
    if name in (
        "chroma_persist",
        "metrics_enabled",
        "tracing_enabled",
        "public_dev_surfaces",
        "offline",
    ):
        return parse_bool(value)
    if name in ("allowed_tenants", "allowed_capabilities"):
        return parse_csv(value)
    if name == "service_token":
        return _coerce_secret(value)
    if name == "data_dir":
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    if name in ("store_overrides", "extra_env"):
        if isinstance(value, Mapping):
            return tuple(value.items())
        return tuple(tuple(item) for item in value)
    return value if value is None else str(value)


# ---------------------------------------------------------------- registry
ProfileFactory = Callable[[], SelfHostProfile]
_REGISTRY: Dict[str, ProfileFactory] = {}
_BUILTINS: Tuple[str, ...] = ("local", "selfhost", "offline", "test")


def register_profile(name: str, factory: ProfileFactory, *, replace_existing: bool = False) -> None:
    """Register a named profile factory (built-ins cannot be replaced)."""

    key = name.strip().lower()
    if not key:
        raise ProfileError("profile name must not be empty")
    if key in _BUILTINS and key in _REGISTRY:
        raise ProfileError(f"built-in profile {key!r} cannot be replaced")
    if key in _REGISTRY and not replace_existing:
        raise ProfileError(f"profile {key!r} is already registered")
    _REGISTRY[key] = factory


def _local() -> SelfHostProfile:
    return SelfHostProfile(
        name="local",
        description="Single-developer workstation: loopback bind, durable SQLite under ./.skeleton/data.",
        environment="development",
        host="127.0.0.1",
        port=8001,
        data_dir=".skeleton/data",
        log_level="INFO",
    )


def _selfhost() -> SelfHostProfile:
    return SelfHostProfile(
        name="selfhost",
        description="Production self-host on one machine: all-interface bind, durable state under /var/lib/skeleton, engine token required.",
        environment="production",
        host="0.0.0.0",
        port=8001,
        data_dir="/var/lib/skeleton",
        chroma_persist=True,
        log_level="INFO",
        metrics_enabled=True,
    )


def _offline() -> SelfHostProfile:
    return SelfHostProfile(
        name="offline",
        description="Standalone/air-gapped: loopback bind, durable state in the user data dir, provider credentials stripped.",
        environment="production",
        host="127.0.0.1",
        port=8001,
        data_dir="~/.local/share/skeleton",
        chroma_persist=True,
        offline=True,
        log_level="INFO",
    )


def _test() -> SelfHostProfile:
    return SelfHostProfile(
        name="test",
        description="Ephemeral test instance: in-memory stores, loopback bind, non-default port.",
        environment="test",
        host="127.0.0.1",
        port=18001,
        data_dir=None,
        metrics_enabled=False,
        log_level="WARNING",
    )


for _name, _factory in (("local", _local), ("selfhost", _selfhost), ("offline", _offline), ("test", _test)):
    _REGISTRY[_name] = _factory


def builtin_profile_names() -> Tuple[str, ...]:
    return _BUILTINS


def list_profiles() -> list[Dict[str, Any]]:
    """Describe every registered profile (redacted)."""

    out = []
    def order(item: str) -> Tuple[int, str]:
        return (_BUILTINS.index(item), "") if item in _BUILTINS else (len(_BUILTINS), item)

    for name in sorted(_REGISTRY, key=order):
        profile = _REGISTRY[name]()
        out.append(
            {
                "name": profile.name,
                "description": profile.description,
                "environment": profile.environment,
                "bind": f"{profile.host}:{profile.port}",
                "durable": profile.durable,
                "offline": profile.offline,
                "builtin": name in _BUILTINS,
            }
        )
    return out


def get_profile(name: str) -> SelfHostProfile:
    key = (name or "").strip().lower()
    factory = _REGISTRY.get(key)
    if factory is None:
        raise ProfileError(f"unknown profile {name!r}; available: {', '.join(sorted(_REGISTRY))}")
    return factory()


def resolve_profile(
    name: str = "local",
    *,
    profile_file: Optional[str] = None,
    env_overlay: Optional[Mapping[str, str]] = None,
    environ: Optional[Mapping[str, str]] = None,
    overrides: Optional[Mapping[str, Any]] = None,
    assignments: Iterable[str] = (),
) -> SelfHostProfile:
    """Resolve the effective profile.

    Precedence (lowest first): named profile or ``profile_file`` → ``env_overlay``
    (an ``.env`` file) → ``environ`` (``SKL_*``/``SKELETON_*`` entries only)
    → ``overrides`` → ``assignments`` (``key=value``).
    """

    if profile_file:
        try:
            document = json.loads(Path(profile_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileError(f"cannot read profile file {profile_file!r}: {exc}") from exc
        profile = SelfHostProfile.from_mapping(document)
    else:
        profile = get_profile(name)
    if env_overlay:
        profile = SelfHostProfile.from_env(env_overlay, base=profile)
    if environ:
        scoped = {k: v for k, v in environ.items() if k in MANAGED_ENV and k != PROFILE_ENV}
        if scoped:
            profile = SelfHostProfile.from_env(scoped, base=profile)
    if overrides:
        clean = {k: v for k, v in overrides.items() if v is not None}
        if clean:
            profile = profile.with_overrides(**clean)
    assignments = list(assignments)
    if assignments:
        profile = profile.with_settings(assignments)
    return profile
