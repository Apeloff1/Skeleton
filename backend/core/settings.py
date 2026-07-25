"""
core/settings.py — Typed, centralized application settings (Stage A2).

Replaces scattered ``os.environ.get(...)`` reads with a single, typed,
validated settings object built on ``pydantic-settings``. Modules that need
configuration should import the cached singleton::

    from core.settings import get_settings
    settings = get_settings()
    if settings.omega_persist:
        ...

Design notes
------------
* Values are read from the process environment (and ``backend/.env`` which is
  already loaded by ``core.databases`` at import time). We DO NOT re-declare or
  mutate the protected env vars (MONGO_URL / DB_NAME / EXPO_* / metro) — we only
  *read* them so the rest of the code has one typed access point.
* ``extra="ignore"`` keeps the object tolerant of the large number of unrelated
  env vars present in the pod (this is an additive, non-breaking layer).
* ``get_settings()`` is ``lru_cache``-d so the object is a process singleton and
  construction cost is paid once (keeps the K8s readiness probe fast).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Typed view over the backend environment.

    Only fields the application actually branches on are declared. Anything
    else in the environment is ignored (``extra="ignore"``).
    """

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Datastore (read-only mirrors of the protected env) ──────────────
    mongo_url: str = "mongodb://localhost:27017"
    db_name: str = "galaxy_studio_db"

    # ── Observability / logging ─────────────────────────────────────────
    log_format: str = ""                 # "json" enables the structured sink
    log_sample_paths: str = ""

    # ── Auth / RBAC ─────────────────────────────────────────────────────
    gameforge_auth_enforce: bool = False

    # ── LLM ─────────────────────────────────────────────────────────────
    emergent_llm_key: str = ""

    # ── Ω-Ultra Conductor fabric (Stage A1) ─────────────────────────────
    omega_persist: bool = True           # persist System-IQ / growth to Mongo
    omega_persist_interval_s: float = 5.0  # throttle window for fabric writes

    # ── Convenience ─────────────────────────────────────────────────────
    @property
    def json_logging(self) -> bool:
        return (self.log_format or "").lower() == "json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached Settings singleton."""
    return Settings()


__all__ = ["Settings", "get_settings"]
