"""Pydantic-settings configuration tree for Skeleton.

Environment-driven, validated at load time. Every subsystem reads its slice
from the tree; nothing reads ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from skeleton.kernel.errors import ConfigurationError


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKL_SERVER_")

    host: str = "0.0.0.0"
    port: int = Field(default=8001, ge=1, le=65535)
    reload: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class MongoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKL_MONGO_")

    uri: str = "mongodb://localhost:27017"
    database: str = "skeleton"
    timeout_ms: int = Field(default=5000, ge=100)


class ChromaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKL_CHROMA_")

    host: str = "localhost"
    port: int = Field(default=8000, ge=1, le=65535)
    collection: str = "skeleton_memory"
    persist_directory: str | None = None


class JeevesSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKL_JEEVES_")

    model: str = "gpt-4o"
    api_key: str | None = None
    max_session_turns: int = Field(default=200, ge=1)
    co_coding_enabled: bool = True
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class PipelineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKL_PIPELINE_")

    max_stages: int = Field(default=12, ge=1)
    default_timeout_s: float = Field(default=120.0, gt=0)
    retry_attempts: int = Field(default=2, ge=0)


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKL_OBS_")

    log_level: str = "INFO"
    metrics_enabled: bool = True
    tracing_enabled: bool = False

    @field_validator("log_level")
    @classmethod
    def _level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"unknown log level {v!r}")
        return v


class Settings(BaseSettings):
    """Root of the configuration tree."""

    model_config = SettingsConfigDict(env_prefix="SKL_", extra="ignore")

    environment: str = "development"
    version: str = "16.2.0"
    server: ServerSettings = Field(default_factory=ServerSettings)
    mongo: MongoSettings = Field(default_factory=MongoSettings)
    chroma: ChromaSettings = Field(default_factory=ChromaSettings)
    jeeves: JeevesSettings = Field(default_factory=JeevesSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        v = v.lower()
        if v not in {"development", "staging", "production", "test"}:
            raise ValueError(f"unknown environment {v!r}")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def summary(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "version": self.version,
            "server": {"host": self.server.host, "port": self.server.port},
            "mongo_database": self.mongo.database,
            "chroma_collection": self.chroma.collection,
            "jeeves_model": self.jeeves.model,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache the settings tree; fails fast on invalid configuration."""
    try:
        return Settings()
    except Exception as exc:  # pydantic ValidationError included
        raise ConfigurationError(
            "Invalid Skeleton configuration",
            context={"detail": str(exc)},
            cause=exc,
        ) from exc
