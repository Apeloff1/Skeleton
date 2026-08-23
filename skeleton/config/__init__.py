"""Configuration tree for Skeleton.

All runtime configuration flows through ``SkeletonSettings``: a single,
validated, environment-driven settings object built on pydantic-settings.
Every subsystem receives exactly the sub-config it needs, injected at
construction — nothing reaches into environment variables directly.

Environment variable mapping (prefix ``SKELETON_``):
    SKELETON_ENV=production
    SKELETON_MONGO__URI=mongodb://localhost:27017
    SKELETON_RAG__BACKEND=chromadb
    SKELETON_AGENTS__HEARTBEAT_TTL_SECONDS=45
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import Any


def _model_config_env(prefix: str) -> dict[str, Any]:
    """Build a settings-compatible env config dict.

    Centralised so a future migration off pydantic-settings touches one place.
    """
    return {"env_prefix": prefix, "env_nested_delimiter": "__", "extra": "ignore"}


class Environment(str, Enum):
    """Deployment environment. Drives logging verbosity and safety rails."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"

    @property
    def is_production_like(self) -> bool:
        return self in (Environment.STAGING, Environment.PRODUCTION)


class LogLevel(str, Enum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


try:  # pydantic-settings path (production)
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class MongoSettings(BaseSettings):
        """MongoDB connection settings."""

        model_config = SettingsConfigDict(**_model_config_env("SKELETON_MONGO_"))

        uri: str = Field(default="mongodb://localhost:27017")
        database: str = Field(default="skeleton")
        max_pool_size: int = Field(default=100, ge=1, le=10000)
        min_pool_size: int = Field(default=10, ge=0)
        server_selection_timeout_ms: int = Field(default=5000, ge=100)
        retry_writes: bool = Field(default=True)

    class RagSettings(BaseSettings):
        """Retrieval-augmented memory settings."""

        model_config = SettingsConfigDict(**_model_config_env("SKELETON_RAG_"))

        backend: str = Field(default="memory")  # "chromadb" | "memory"
        chroma_path: str = Field(default=".chroma")
        collection: str = Field(default="jeeves_memory")
        chunk_size: int = Field(default=512, ge=64)
        chunk_overlap: int = Field(default=64, ge=0)
        top_k: int = Field(default=5, ge=1, le=100)

    class AgentSettings(BaseSettings):
        """Agent mesh / scheduler tuning."""

        model_config = SettingsConfigDict(**_model_config_env("SKELETON_AGENTS_"))

        heartbeat_ttl_seconds: float = Field(default=30.0, gt=0)
        max_in_flight: int = Field(default=64, ge=1)
        max_retries: int = Field(default=3, ge=0)
        backoff_base_seconds: float = Field(default=0.5, gt=0)
        backoff_cap_seconds: float = Field(default=30.0, gt=0)
        ledger_capacity: int = Field(default=100_000, ge=100)

    class PipelineSettings(BaseSettings):
        """Pipeline engine tuning."""

        model_config = SettingsConfigDict(**_model_config_env("SKELETON_PIPELINE_"))

        default_seed: int = Field(default=1337)
        max_stage_seconds: float = Field(default=60.0, gt=0)
        balance_simulation_rounds: int = Field(default=500, ge=10)

    class ApiSettings(BaseSettings):
        """HTTP interface settings."""

        model_config = SettingsConfigDict(**_model_config_env("SKELETON_API_"))

        host: str = Field(default="0.0.0.0")
        port: int = Field(default=8001, ge=1, le=65535)
        cors_origins: list[str] = Field(default_factory=lambda: ["*"])
        request_timeout_seconds: float = Field(default=55.0, gt=0)

    class SkeletonSettings(BaseSettings):
        """Root settings object for the whole platform."""

        model_config = SettingsConfigDict(**_model_config_env("SKELETON_"))

        env: Environment = Field(default=Environment.DEVELOPMENT)
        log_level: LogLevel = Field(default=LogLevel.INFO)
        service_name: str = Field(default="skeleton")
        version: str = Field(default="16.0.0")

        mongo: MongoSettings = Field(default_factory=MongoSettings)
        rag: RagSettings = Field(default_factory=RagSettings)
        agents: AgentSettings = Field(default_factory=AgentSettings)
        pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
        api: ApiSettings = Field(default_factory=ApiSettings)

except ImportError:  # pragma: no cover - exercised only without pydantic
    from dataclasses import dataclass, field

    @dataclass(frozen=True)
    class MongoSettings:  # type: ignore[no-redef]
        uri: str = "mongodb://localhost:27017"
        database: str = "skeleton"
        max_pool_size: int = 100
        min_pool_size: int = 10
        server_selection_timeout_ms: int = 5000
        retry_writes: bool = True

    @dataclass(frozen=True)
    class RagSettings:  # type: ignore[no-redef]
        backend: str = "memory"
        chroma_path: str = ".chroma"
        collection: str = "jeeves_memory"
        chunk_size: int = 512
        chunk_overlap: int = 64
        top_k: int = 5

    @dataclass(frozen=True)
    class AgentSettings:  # type: ignore[no-redef]
        heartbeat_ttl_seconds: float = 30.0
        max_in_flight: int = 64
        max_retries: int = 3
        backoff_base_seconds: float = 0.5
        backoff_cap_seconds: float = 30.0
        ledger_capacity: int = 100_000

    @dataclass(frozen=True)
    class PipelineSettings:  # type: ignore[no-redef]
        default_seed: int = 1337
        max_stage_seconds: float = 60.0
        balance_simulation_rounds: int = 500

    @dataclass(frozen=True)
    class ApiSettings:  # type: ignore[no-redef]
        host: str = "0.0.0.0"
        port: int = 8001
        cors_origins: list[str] = field(default_factory=lambda: ["*"])
        request_timeout_seconds: float = 55.0

    @dataclass(frozen=True)
    class SkeletonSettings:  # type: ignore[no-redef]
        env: Environment = Environment.DEVELOPMENT
        log_level: LogLevel = LogLevel.INFO
        service_name: str = "skeleton"
        version: str = "16.0.0"
        mongo: MongoSettings = field(default_factory=MongoSettings)
        rag: RagSettings = field(default_factory=RagSettings)
        agents: AgentSettings = field(default_factory=AgentSettings)
        pipeline: PipelineSettings = field(default_factory=PipelineSettings)
        api: ApiSettings = field(default_factory=ApiSettings)


@lru_cache(maxsize=1)
def get_settings() -> SkeletonSettings:
    """Return the process-wide settings singleton (cached)."""
    return SkeletonSettings()


def reset_settings_cache() -> None:
    """Drop the cached settings object. Used by tests that mutate the env."""
    get_settings.cache_clear()
    # Keep ``os`` referenced so static analysis treats it as used even when
    # pydantic-settings swallows environment handling internally.
    _ = os.environ
