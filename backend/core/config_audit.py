"""Startup configuration audit: names risky settings, never their values.

``audit_config`` is a pure function over an environment mapping. It returns
:class:`ConfigFinding` records. ``log_config_audit`` writes one WARNING line per
finding and is called from the FastAPI lifespan. The audit is
**advisory**: it never raises, never blocks boot and never changes behaviour
(for example the provenance-ledger key derivation is untouched; the audit
only warns when it is relying on its fallback).

Findings carry a stable ``code`` so dashboards and tests can match them.
Messages mention variable names only, so the output is safe for any log sink.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urlsplit

Severity = Literal["warning", "error"]

_PRODUCTION = frozenset({"prod", "production"})
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})
_MIN_SECRET_CHARS = 32
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "mongo", "mongodb"})


@dataclass(frozen=True, slots=True)
class ConfigFinding:
    code: str
    severity: Severity
    variable: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def environment_name(env: Mapping[str, str]) -> str:
    return (env.get("APP_ENV") or env.get("ENVIRONMENT") or "development").strip().lower() or "development"


def _configured(env: Mapping[str, str], name: str) -> bool:
    return bool(env.get(name, "").strip() or env.get(f"{name}_FILE", "").strip())


def _flag(env: Mapping[str, str], name: str) -> bool | None:
    raw = env.get(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return None


def audit_config(env: Mapping[str, str] | None = None) -> list[ConfigFinding]:
    """Return findings for ``env`` (defaults to ``os.environ``)."""

    source: Mapping[str, str] = os.environ if env is None else env
    production = environment_name(source) in _PRODUCTION
    findings: list[ConfigFinding] = []

    def add(code: str, severity: Severity, variable: str, message: str) -> None:
        findings.append(ConfigFinding(code, severity, variable, message))

    provenance = source.get("PROVENANCE_SECRET", "")
    if production and not provenance.strip():
        add(
            "provenance_secret_unset",
            "warning",
            "PROVENANCE_SECRET",
            "PROVENANCE_SECRET is unset in production; the provenance chain MAC is keyed from the "
            "MONGO_URL fallback, so anyone who knows the connection string can recompute chain heads. "
            "Set a dedicated high-entropy secret (existing chains keep their current key until migrated).",
        )
    elif provenance.strip() and len(provenance.strip()) < _MIN_SECRET_CHARS:
        add(
            "provenance_secret_weak",
            "warning",
            "PROVENANCE_SECRET",
            f"PROVENANCE_SECRET is shorter than {_MIN_SECRET_CHARS} characters.",
        )

    enforce = _flag(source, "GAMEFORGE_AUTH_ENFORCE")
    if source.get("GAMEFORGE_AUTH_ENFORCE") is not None and enforce is None:
        add(
            "auth_enforce_invalid",
            "error",
            "GAMEFORGE_AUTH_ENFORCE",
            "GAMEFORGE_AUTH_ENFORCE is not a boolean flag; authentication configuration will be rejected.",
        )
    auth_on = enforce if enforce is not None else production
    if production and enforce is False:
        add(
            "auth_disabled_in_production",
            "warning",
            "GAMEFORGE_AUTH_ENFORCE",
            "GAMEFORGE_AUTH_ENFORCE explicitly disables authentication in production.",
        )
    if auth_on and not _configured(source, "GAMEFORGE_JWT_SECRET"):
        add(
            "jwt_secret_missing",
            "error",
            "GAMEFORGE_JWT_SECRET",
            "Authentication is enforced but neither GAMEFORGE_JWT_SECRET nor GAMEFORGE_JWT_SECRET_FILE is set.",
        )

    if production:
        mongo_url = source.get("MONGO_URL", "").strip()
        host = (urlsplit(mongo_url).hostname or "").lower() if mongo_url else ""
        if not mongo_url or host in _LOCAL_HOSTS:
            add(
                "mongo_url_local_default",
                "warning",
                "MONGO_URL",
                "MONGO_URL is unset or points at a local default host in production.",
            )
        cors = source.get("CORS_ORIGINS", "*").strip()
        if cors in {"", "*"}:
            add(
                "cors_wildcard_in_production",
                "warning",
                "CORS_ORIGINS",
                "CORS_ORIGINS allows every origin in production; list the real front-end origins.",
            )

    if _configured(source, "STRIPE_API_KEY") and not _configured(source, "STRIPE_WEBHOOK_SECRET"):
        add(
            "stripe_webhook_secret_missing",
            "warning",
            "STRIPE_WEBHOOK_SECRET",
            "STRIPE_API_KEY is set without STRIPE_WEBHOOK_SECRET; payment webhooks cannot be verified "
            "and will answer as unavailable.",
        )
    return findings


def log_config_audit(logger: logging.Logger | None = None, env: Mapping[str, str] | None = None) -> list[ConfigFinding]:
    """Log each finding at WARNING (``error`` severity included) and return them.

    Never raises: an audit failure is itself logged and yields ``[]``.
    """

    log = logger or logging.getLogger("codedock.config_audit")
    try:
        findings = audit_config(env)
    except Exception as exc:  # pragma: no cover - defensive; audit must not block boot
        log.warning("config audit failed: %s", type(exc).__name__)
        return []
    for finding in findings:
        log.warning(
            "config audit [%s] %s %s: %s",
            finding.severity,
            finding.code,
            finding.variable,
            finding.message,
        )
    if not findings:
        log.info("config audit: no findings (environment=%s)", environment_name(os.environ if env is None else env))
    return findings


__all__ = ["ConfigFinding", "audit_config", "environment_name", "log_config_audit"]
