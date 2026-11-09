"""Typed, validated runtime configuration per deployment environment.

One canonical loader for dev / staging / prod. Values come only from the
process environment (or an explicit mapping in tests); no secret has a default.
Validation is strict outside development so a misconfigured staging/prod
container fails at boot instead of serving with unsafe settings.

Secret names (values are never committed; supply via the deploy platform):
    MONGO_URL, JWT_SECRET, ADVANCED_API_TOKEN, OPS_TOKEN, OPENAI_API_KEY,
    STRIPE_API_KEY, STRIPE_WEBHOOK_SECRET, GAMEFORGE_JWT_SECRET, GF_SEAL_SECRET,
    GF_KEYHOLDER_SEED, SKL_ENGINE_SERVICE_TOKEN
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlparse

ENVIRONMENTS = ("development", "staging", "production")
_ALIASES = {"dev": "development", "local": "development", "stage": "staging", "prod": "production"}
SECRET_NAMES = (
    "MONGO_URL", "JWT_SECRET", "ADVANCED_API_TOKEN", "OPS_TOKEN",
    "OPENAI_API_KEY", "STRIPE_API_KEY", "STRIPE_WEBHOOK_SECRET",
    "GAMEFORGE_JWT_SECRET", "GF_SEAL_SECRET", "GF_KEYHOLDER_SEED", "SKL_ENGINE_SERVICE_TOKEN",
)
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_MIN_SECRET_LEN = 32


class ConfigError(ValueError):
    """Raised with every validation problem found, not just the first."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("invalid runtime configuration:\n  - " + "\n  - ".join(problems))


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    app_version: str
    host: str
    port: int
    log_level: str
    log_json: bool
    mongo_url: str
    db_name: str
    cors_origins: tuple[str, ...]
    metrics_enabled: bool
    jwt_secret: str = field(repr=False)
    ops_token: str = field(repr=False)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def redacted(self) -> dict:
        """Safe-to-log view: secrets reduced to set/unset."""
        out = {k: getattr(self, k) for k in self.__dataclass_fields__}
        for k in ("jwt_secret", "ops_token"):
            out[k] = "set" if out[k] else "unset"
        parsed = urlparse(self.mongo_url) if self.mongo_url else None
        out["mongo_url"] = f"{parsed.scheme}://{parsed.hostname}" if parsed and parsed.hostname else "unset"
        out["cors_origins"] = list(self.cors_origins)
        return out


def normalize_environment(raw: str | None) -> str:
    value = (raw or "development").strip().lower()
    return _ALIASES.get(value, value)


def _bool(raw: str | None, default: bool, name: str, problems: list[str]) -> bool:
    if raw is None or raw.strip() == "":
        return default
    v = raw.strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    problems.append(f"{name} must be a boolean (got {raw!r})")
    return default


def load_runtime_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    src = os.environ if env is None else env
    get = lambda k, d="": (src.get(k) or d).strip()  # noqa: E731
    problems: list[str] = []

    environment = normalize_environment(src.get("ENVIRONMENT"))
    if environment not in ENVIRONMENTS:
        problems.append(f"ENVIRONMENT must be one of {ENVIRONMENTS} (got {environment!r})")
    strict = environment in ("staging", "production")

    port_raw = get("PORT", "8001")
    try:
        port = int(port_raw)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        problems.append(f"PORT must be an integer 1-65535 (got {port_raw!r})")
        port = 8001

    log_level = get("LOG_LEVEL", "DEBUG" if environment == "development" else "INFO").upper()
    if log_level not in LOG_LEVELS:
        problems.append(f"LOG_LEVEL must be one of {LOG_LEVELS} (got {log_level!r})")

    mongo_url = get("MONGO_URL", "" if strict else "mongodb://localhost:27017")
    if not mongo_url:
        problems.append("MONGO_URL is required in staging/production")
    elif urlparse(mongo_url).scheme not in ("mongodb", "mongodb+srv"):
        problems.append("MONGO_URL must use the mongodb:// or mongodb+srv:// scheme")

    cors = tuple(o.strip() for o in get("CORS_ORIGINS", "*").split(",") if o.strip()) or ("*",)
    if strict and "*" in cors:
        problems.append("CORS_ORIGINS must be an explicit origin list in staging/production")
    for origin in cors:
        if origin != "*" and urlparse(origin).scheme not in ("http", "https"):
            problems.append(f"CORS origin {origin!r} must be an http(s) URL")
        if environment == "production" and origin.startswith("http://"):
            problems.append(f"CORS origin {origin!r} must use https in production")

    jwt_secret = get("JWT_SECRET")
    if strict and len(jwt_secret) < _MIN_SECRET_LEN:
        problems.append(f"JWT_SECRET must be set and at least {_MIN_SECRET_LEN} characters in staging/production")
    ops_token = get("OPS_TOKEN")
    if strict and len(ops_token) < _MIN_SECRET_LEN:
        problems.append(f"OPS_TOKEN must be set and at least {_MIN_SECRET_LEN} characters in staging/production")

    log_json = _bool(src.get("LOG_JSON"), strict, "LOG_JSON", problems)
    metrics_enabled = _bool(src.get("METRICS_ENABLED"), True, "METRICS_ENABLED", problems)

    if problems:
        raise ConfigError(problems)
    return RuntimeConfig(
        environment=environment,
        app_version=get("APP_VERSION", "dev"),
        host=get("HOST", "0.0.0.0"),
        port=port,
        log_level=log_level,
        log_json=log_json,
        mongo_url=mongo_url,
        db_name=get("DB_NAME", "tutolage"),
        cors_origins=cors,
        jwt_secret=jwt_secret,
        ops_token=ops_token,
        metrics_enabled=metrics_enabled,
    )
