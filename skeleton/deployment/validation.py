"""Fail-closed validation of self-host profiles.

:func:`validate_profile` turns a :class:`~skeleton.deployment.profile.SelfHostProfile`
into a :class:`ValidationReport` of coded issues. Rules mirror the constraints
the runtime enforces at load time (``skeleton.config.settings``), the
security posture of the shipped container (``docker-compose.yml`` demands an
engine token and authenticated Mongo) and operational hazards specific to
self-hosting (in-memory durable stores in production, colliding store files,
dev surfaces exposed on a public bind).

Every issue has a stable ``code`` so operators and tests can match on it
without parsing messages. ``ERROR`` issues block boot; ``WARNING`` issues are
reported but never block.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

from .profile import ENVIRONMENTS, LOG_LEVELS, MANAGED_ENV, MEMORY_PATH, SelfHostProfile

__all__ = [
    "DeploymentConfigError",
    "Issue",
    "RULES",
    "Severity",
    "ValidationReport",
    "is_loopback_host",
    "parse_mongo_uri",
    "validate_against_settings",
    "validate_profile",
]

MIN_TOKEN_LENGTH = 32
MIN_TOKEN_DISTINCT = 10
DISK_WARN_BYTES = 512 * 1024 * 1024
DISK_FAIL_BYTES = 64 * 1024 * 1024

_HOSTNAME_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_PRINCIPAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_MONGO_DB_FORBIDDEN = set('/\\. "$*<>:|?')

#: Stable rule catalogue: code -> short description (documentation + tests).
RULES: Dict[str, str] = {
    "DEP001": "environment must be one of development/staging/production/test",
    "DEP002": "server port must be within 1..65535",
    "DEP003": "privileged port requires root or CAP_NET_BIND_SERVICE",
    "DEP004": "server host must be an IP address or RFC 1123 hostname",
    "DEP005": "all-interface bind outside production/staging",
    "DEP006": "log level must be a standard logging level",
    "DEP007": "DEBUG logging in production",
    "DEP010": "engine service token must be normalized and >= 32 characters",
    "DEP011": "engine service token is required in production",
    "DEP012": "engine service token recommended in staging / on public binds",
    "DEP013": "engine service token has low character diversity",
    "DEP014": "engine service principal must be a simple identifier",
    "DEP020": "durable state required in production/staging (no data_dir)",
    "DEP021": "store resolves to :memory: in production/staging",
    "DEP022": "two stores share one file",
    "DEP023": "relative store path override",
    "DEP024": "workers must be >= 1",
    "DEP025": "multiple workers with in-memory stores lose state between workers",
    "DEP030": "Mongo URI must use mongodb:// or mongodb+srv:// and name a host",
    "DEP031": "Mongo URI without credentials in production",
    "DEP032": "Mongo database name is invalid",
    "DEP033": "offline profile points at a non-local Mongo host",
    "DEP040": "Chroma port must be within 1..65535",
    "DEP041": "Chroma persistence requires a data_dir",
    "DEP042": "offline profile points at a non-local Chroma host",
    "DEP050": "engine allow-list must not be empty",
    "DEP051": "wildcard engine allow-list in production",
    "DEP060": "public dev surfaces must not be enabled in production",
    "DEP061": "public dev surfaces enabled in staging / on a public bind",
    "DEP070": "extra_env key is not a valid environment variable name",
    "DEP071": "extra_env shadows a profile-managed variable",
    "DEP072": "offline profile forwards a provider credential via extra_env",
    "DEP080": "data directory is not writable",
    "DEP081": "low free disk space under data directory",
    "DEP082": "data directory path exists and is not a directory",
    "DEP090": "runtime settings tree rejects the rendered environment",
    "DEP091": "runtime settings tree unavailable (pydantic not importable)",
}


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    field: str
    message: str
    hint: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "field": self.field,
            "message": self.message,
            "hint": self.hint,
        }


@dataclass
class ValidationReport:
    profile: str
    fingerprint: str
    issues: List[Issue] = field(default_factory=list)

    @property
    def errors(self) -> List[Issue]:
        return [item for item in self.issues if item.severity is Severity.ERROR]

    @property
    def warnings(self) -> List[Issue]:
        return [item for item in self.issues if item.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> List[str]:
        return [item.code for item in self.issues]

    def add(self, code: str, severity: Severity, field_name: str, message: str, hint: str = "") -> None:
        if code not in RULES:
            raise KeyError(f"unregistered validation rule {code}")
        self.issues.append(Issue(code, severity, field_name, message, hint))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "deployment_validation",
            "profile": self.profile,
            "fingerprint": self.fingerprint,
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [item.to_dict() for item in self.issues],
        }

    def raise_for_errors(self) -> "ValidationReport":
        if not self.ok:
            raise DeploymentConfigError(self)
        return self


class DeploymentConfigError(ValueError):
    """Raised when a profile has blocking validation errors."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        summary = "; ".join(f"{i.code} {i.field}: {i.message}" for i in report.errors)
        super().__init__(f"profile {report.profile!r} is invalid: {summary}")


# ------------------------------------------------------------------ helpers
def is_loopback_host(host: str) -> bool:
    text = host.strip().strip("[]").lower()
    if text in ("localhost", "localhost.localdomain"):
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _is_private_or_loopback(host: str) -> bool:
    if is_loopback_host(host):
        return True
    text = host.strip().strip("[]")
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return text.endswith(".local") or text.endswith(".internal") or "." not in text
    return address.is_private or address.is_link_local


def _is_wildcard_bind(host: str) -> bool:
    return host.strip() in ("0.0.0.0", "::", "[::]", "")


def _valid_host(host: str) -> bool:
    text = host.strip()
    if not text:
        return False
    try:
        ipaddress.ip_address(text.strip("[]"))
        return True
    except ValueError:
        pass
    if len(text) > 253:
        return False
    labels = text.rstrip(".").split(".")
    return all(_HOSTNAME_LABEL.match(label) for label in labels)


def parse_mongo_uri(uri: str) -> Tuple[str, List[Tuple[str, int]], bool]:
    """Return ``(scheme, [(host, port)], has_credentials)`` for a Mongo URI.

    Handles the multi-host seed-list form (``host1:27017,host2:27018``) that
    :func:`urllib.parse.urlsplit` cannot parse as a single netloc.
    """

    if "://" not in uri:
        raise ValueError("missing scheme")
    scheme, rest = uri.split("://", 1)
    scheme = scheme.lower()
    netloc = rest.split("/", 1)[0].split("?", 1)[0]
    has_credentials = "@" in netloc
    hostlist = netloc.rpartition("@")[2]
    hosts: List[Tuple[str, int]] = []
    for item in hostlist.split(","):
        item = item.strip()
        if not item:
            continue
        if item.startswith("["):
            end = item.find("]")
            if end < 0:
                raise ValueError(f"bad IPv6 host {item!r}")
            host = item[1:end]
            port_text = item[end + 2:] if item[end + 1:end + 2] == ":" else ""
        elif item.count(":") == 1:
            host, port_text = item.split(":", 1)
        else:
            host, port_text = item, ""
        port = 27017
        if port_text:
            if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
                raise ValueError(f"bad port in {item!r}")
            port = int(port_text)
        hosts.append((host, port))
    if not hosts:
        raise ValueError("no host")
    return scheme, hosts, has_credentials


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            break
        current = current.parent
    return current


# ------------------------------------------------------------------- rules
def _check_server(profile: SelfHostProfile, report: ValidationReport) -> None:
    if profile.environment not in ENVIRONMENTS:
        report.add("DEP001", Severity.ERROR, "environment", f"unknown environment {profile.environment!r}",
                   f"use one of {', '.join(ENVIRONMENTS)}")
    if not 1 <= profile.port <= 65535:
        report.add("DEP002", Severity.ERROR, "port", f"port {profile.port} is out of range")
    elif profile.port < 1024 and hasattr(os, "geteuid") and os.geteuid() != 0:
        report.add("DEP003", Severity.WARNING, "port", f"port {profile.port} is privileged",
                   "bind >= 1024 and front it with a reverse proxy, or grant CAP_NET_BIND_SERVICE")
    if not _valid_host(profile.host):
        report.add("DEP004", Severity.ERROR, "host", f"invalid host {profile.host!r}")
    elif _is_wildcard_bind(profile.host) and profile.environment in ("development", "test"):
        report.add("DEP005", Severity.WARNING, "host", "binding all interfaces in a non-production profile",
                   "use 127.0.0.1 unless the instance must be reachable from the network")
    if profile.log_level not in LOG_LEVELS:
        report.add("DEP006", Severity.ERROR, "log_level", f"unknown log level {profile.log_level!r}")
    elif profile.log_level == "DEBUG" and profile.is_production:
        report.add("DEP007", Severity.WARNING, "log_level", "DEBUG logging may record request payloads in production")
    if profile.workers < 1:
        report.add("DEP024", Severity.ERROR, "workers", "workers must be >= 1")
    elif profile.workers > 1 and not profile.durable:
        report.add("DEP025", Severity.WARNING, "workers",
                   "each worker gets its own in-memory stores; state is not shared",
                   "set data_dir so every worker binds the same SQLite files")


def _check_token(profile: SelfHostProfile, report: ValidationReport) -> None:
    token = profile.service_token.reveal()
    public = _is_wildcard_bind(profile.host) or not is_loopback_host(profile.host)
    if token:
        if token != token.strip() or len(token) < MIN_TOKEN_LENGTH:
            report.add("DEP010", Severity.ERROR, "service_token",
                       f"token must have no surrounding whitespace and be at least {MIN_TOKEN_LENGTH} characters",
                       "generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'")
        elif len(set(token)) < MIN_TOKEN_DISTINCT:
            report.add("DEP013", Severity.WARNING, "service_token", "token has very few distinct characters")
    elif profile.is_production:
        report.add("DEP011", Severity.ERROR, "service_token",
                   "production requires SKL_ENGINE_SERVICE_TOKEN (the engine API is fail-closed)",
                   "set SKL_ENGINE_SERVICE_TOKEN in the environment or env file")
    elif profile.environment == "staging" or (public and profile.environment != "test"):
        report.add("DEP012", Severity.WARNING, "service_token",
                   "no engine service token; engine routes will reject every caller")
    if not _PRINCIPAL.match(profile.service_principal or ""):
        report.add("DEP014", Severity.ERROR, "service_principal",
                   f"invalid service principal {profile.service_principal!r}")


def _check_stores(profile: SelfHostProfile, report: ValidationReport) -> None:
    durable_required = profile.environment in ("production", "staging")
    if durable_required and profile.data_dir is None:
        report.add("DEP020", Severity.ERROR, "data_dir",
                   f"{profile.environment} requires a data_dir; in-memory stores lose every operation on restart")
    paths = profile.store_paths()
    seen: Dict[str, str] = {}
    for key, path in paths.items():
        if path == MEMORY_PATH:
            if durable_required and profile.data_dir is not None:
                report.add("DEP021", Severity.ERROR, f"store.{key}", f"store {key} is in-memory in {profile.environment}")
            continue
        normalized = os.path.normcase(os.path.abspath(os.path.expanduser(path)))
        if normalized in seen:
            report.add("DEP022", Severity.ERROR, f"store.{key}",
                       f"store {key} shares {path!r} with store {seen[normalized]}")
        else:
            seen[normalized] = key
    for key, path in profile.store_overrides:
        if path != MEMORY_PATH and not os.path.isabs(os.path.expanduser(path)):
            report.add("DEP023", Severity.WARNING, f"store.{key}",
                       f"relative store path {path!r} depends on the working directory")


def _check_mongo(profile: SelfHostProfile, report: ValidationReport) -> None:
    uri = profile.mongo_uri.strip()
    if uri:
        try:
            scheme, hosts, has_credentials = parse_mongo_uri(uri)
        except ValueError as exc:
            report.add("DEP030", Severity.ERROR, "mongo_uri", f"unparseable Mongo URI: {exc}")
        else:
            if scheme not in ("mongodb", "mongodb+srv"):
                report.add("DEP030", Severity.ERROR, "mongo_uri", f"unsupported Mongo scheme {scheme!r}")
            elif any(not host for host, _port in hosts):
                report.add("DEP030", Severity.ERROR, "mongo_uri", "Mongo URI names an empty host")
            else:
                if profile.is_production and not has_credentials:
                    report.add("DEP031", Severity.WARNING, "mongo_uri",
                               "production Mongo URI has no credentials",
                               "use an authenticated URI (docker-compose requires one)")
                if profile.offline and not all(_is_private_or_loopback(h) for h, _p in hosts):
                    report.add("DEP033", Severity.WARNING, "mongo_uri",
                               "offline profile connects to a public Mongo host")
    name = profile.mongo_database
    if not name or len(name) > 63 or any(ch in _MONGO_DB_FORBIDDEN for ch in name) or "\x00" in name:
        report.add("DEP032", Severity.ERROR, "mongo_database", f"invalid Mongo database name {name!r}")


def _check_chroma(profile: SelfHostProfile, report: ValidationReport) -> None:
    if not 1 <= profile.chroma_port <= 65535:
        report.add("DEP040", Severity.ERROR, "chroma_port", f"chroma port {profile.chroma_port} is out of range")
    if profile.chroma_persist and profile.data_dir is None:
        report.add("DEP041", Severity.ERROR, "chroma_persist", "chroma_persist requires data_dir")
    if profile.offline and not _is_private_or_loopback(profile.chroma_host):
        report.add("DEP042", Severity.WARNING, "chroma_host", "offline profile points at a public Chroma host")


def _check_allow_lists(profile: SelfHostProfile, report: ValidationReport) -> None:
    for name in ("allowed_tenants", "allowed_capabilities"):
        values = getattr(profile, name)
        if not values:
            report.add("DEP050", Severity.ERROR, name, f"{name} must contain at least one entry")
        elif "*" in values and profile.is_production:
            report.add("DEP051", Severity.WARNING, name, f"{name} is a wildcard in production",
                       "list the tenants/capabilities this instance serves")


def _check_dev_surfaces(profile: SelfHostProfile, report: ValidationReport) -> None:
    if not profile.public_dev_surfaces:
        return
    if profile.is_production:
        report.add("DEP060", Severity.ERROR, "public_dev_surfaces",
                   "public dev surfaces (/docs, /api/v1/genesis, ...) bypass the HMAC gate")
    elif profile.environment == "staging" or not is_loopback_host(profile.host):
        report.add("DEP061", Severity.WARNING, "public_dev_surfaces",
                   "public dev surfaces are reachable from the network")


def _check_extra_env(profile: SelfHostProfile, report: ValidationReport) -> None:
    from .profile import PROVIDER_KEY_ENV

    for key, _value in profile.extra_env:
        if not _ENV_NAME.match(key):
            report.add("DEP070", Severity.ERROR, f"extra_env.{key}", f"invalid environment variable name {key!r}")
        elif key in MANAGED_ENV:
            report.add("DEP071", Severity.ERROR, f"extra_env.{key}",
                       f"{key} is managed by the profile; set the profile field instead")
        elif profile.offline and key in PROVIDER_KEY_ENV:
            report.add("DEP072", Severity.ERROR, f"extra_env.{key}",
                       f"offline profile must not forward provider credential {key}")


def _check_filesystem(profile: SelfHostProfile, report: ValidationReport) -> None:
    root = profile.data_path()
    if root is None:
        return
    if root.exists() and not root.is_dir():
        report.add("DEP082", Severity.ERROR, "data_dir", f"{root} exists and is not a directory")
        return
    anchor = _nearest_existing(root)
    if not os.access(anchor, os.W_OK | os.X_OK):
        report.add("DEP080", Severity.ERROR, "data_dir", f"{anchor} is not writable by uid {os.getuid() if hasattr(os, 'getuid') else '?'}")
        return
    try:
        free = shutil.disk_usage(anchor).free
    except OSError:
        return
    if free < DISK_FAIL_BYTES:
        report.add("DEP081", Severity.ERROR, "data_dir", f"only {free // (1024 * 1024)} MiB free under {anchor}")
    elif free < DISK_WARN_BYTES:
        report.add("DEP081", Severity.WARNING, "data_dir", f"only {free // (1024 * 1024)} MiB free under {anchor}")


@contextmanager
def _scoped_environ(env: Mapping[str, str]) -> Iterator[None]:
    """Temporarily replace every ``SKL_*`` variable with ``env`` (CLI use only)."""

    saved = {k: v for k, v in os.environ.items() if k.startswith("SKL_")}
    try:
        for key in saved:
            del os.environ[key]
        for key, value in env.items():
            if key.startswith("SKL_"):
                os.environ[key] = value
        yield
    finally:
        for key in [k for k in os.environ if k.startswith("SKL_")]:
            del os.environ[key]
        os.environ.update(saved)


def validate_against_settings(profile: SelfHostProfile, report: Optional[ValidationReport] = None) -> ValidationReport:
    """Load ``skeleton.config.settings.Settings`` from the rendered environment.

    This is the authoritative parity check: whatever the runtime would reject
    at startup is reported here as ``DEP090`` before any process is spawned.
    The process environment is swapped for the duration of the call, so this
    must not run concurrently with code reading ``SKL_*`` variables.
    """

    report = report or ValidationReport(profile.name, profile.fingerprint())
    try:
        from pydantic import ValidationError
        from skeleton.config.settings import Settings
    except ImportError as exc:  # pragma: no cover - pydantic is a hard dependency
        report.add("DEP091", Severity.WARNING, "settings", f"settings tree unavailable: {exc}")
        return report
    env = profile.to_env(include_secrets=True)
    with _scoped_environ(env):
        try:
            settings = Settings()
            settings.engine.allowed_tenants  # noqa: B018 - property validates CSV
            settings.engine.allowed_capabilities  # noqa: B018
        except ValidationError as exc:
            for error in exc.errors():
                location = ".".join(str(part) for part in error.get("loc", ())) or "settings"
                report.add("DEP090", Severity.ERROR, location, str(error.get("msg", "invalid value")))
        except ValueError as exc:
            report.add("DEP090", Severity.ERROR, "settings", str(exc))
    return report


def validate_profile(
    profile: SelfHostProfile,
    *,
    check_filesystem: bool = False,
    check_settings: bool = False,
) -> ValidationReport:
    """Validate ``profile``; optional filesystem and runtime-settings parity checks."""

    report = ValidationReport(profile.name, profile.fingerprint())
    _check_server(profile, report)
    _check_token(profile, report)
    _check_stores(profile, report)
    _check_mongo(profile, report)
    _check_chroma(profile, report)
    _check_allow_lists(profile, report)
    _check_dev_surfaces(profile, report)
    _check_extra_env(profile, report)
    if check_filesystem:
        _check_filesystem(profile, report)
    if check_settings:
        validate_against_settings(profile, report)
    return report
