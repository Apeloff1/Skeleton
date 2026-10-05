"""Deterministic provider registry for the canonical model router.

The registry owns declarative provider metadata only. Adapter construction stays
with the caller so credentials and execution authority never enter persisted
configuration.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import CanonicalContractError, canonical_json_bytes

from skeleton.frontier.runtime.model_routing import ModelRouter, ProviderMetadata, ProviderMetadataError
from skeleton.frontier.runtime.model_runtime import ProviderAdapter

REGISTRY_SCHEMA_VERSION = 1


def _metadata_dict(item: ProviderMetadata) -> dict[str, Any]:
    return {
        "provider_id": item.provider_id,
        "adapter_name": item.adapter_name,
        "model": item.model,
        "capabilities": sorted(item.capabilities),
        "max_input_tokens": item.max_input_tokens,
        "max_output_tokens": item.max_output_tokens,
        "input_cost_per_million": item.input_cost_per_million,
        "output_cost_per_million": item.output_cost_per_million,
        "timeout_seconds": item.timeout_seconds,
        "priority": item.priority,
        "enabled": item.enabled,
        "max_attempts": item.max_attempts,
        "backoff_seconds": item.backoff_seconds,
    }


@dataclass(frozen=True, slots=True)
class RouterRegistrySnapshot:
    providers: tuple[ProviderMetadata, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "providers": [_metadata_dict(item) for item in self.providers],
            "digest": self.digest,
        }


class RouterRegistry:
    """Fail-closed, deterministic registry of provider routing metadata."""

    def __init__(self, providers: Iterable[ProviderMetadata | Mapping[str, Any]] = ()) -> None:
        parsed: dict[str, ProviderMetadata] = {}
        adapter_names: dict[str, str] = {}
        for raw in providers:
            item = raw if isinstance(raw, ProviderMetadata) else ProviderMetadata.from_mapping(raw)
            if item.provider_id in parsed:
                raise ProviderMetadataError(f"duplicate provider_id: {item.provider_id}")
            owner = adapter_names.get(item.adapter_name)
            if owner is not None:
                raise ProviderMetadataError(
                    f"adapter_name {item.adapter_name!r} is shared by {owner!r} and {item.provider_id!r}"
                )
            parsed[item.provider_id] = item
            adapter_names[item.adapter_name] = item.provider_id
        self._providers = parsed

    def providers(self) -> tuple[ProviderMetadata, ...]:
        return tuple(self._providers[key] for key in sorted(self._providers))

    def snapshot(self) -> RouterRegistrySnapshot:
        providers = self.providers()
        body = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "providers": [_metadata_dict(item) for item in providers],
        }
        return RouterRegistrySnapshot(
            providers=providers,
            digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
        )

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> "RouterRegistry":
        if not isinstance(payload, Mapping):
            raise ProviderMetadataError("registry snapshot must be a mapping")
        if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise ProviderMetadataError("unsupported registry schema version")
        rows = payload.get("providers")
        digest = payload.get("digest")
        if not isinstance(rows, list) or not isinstance(digest, str):
            raise ProviderMetadataError("malformed registry snapshot")
        body = {"schema_version": REGISTRY_SCHEMA_VERSION, "providers": rows}
        try:
            actual_digest = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        except CanonicalContractError as exc:
            raise ProviderMetadataError("registry snapshot is not strict canonical JSON") from exc
        if actual_digest != digest:
            raise ProviderMetadataError("registry snapshot digest mismatch")
        return cls(rows)

    def bind(
        self,
        adapters: Mapping[str, ProviderAdapter],
        *,
        router: ModelRouter | None = None,
    ) -> ModelRouter:
        """Bind exact declared adapters to a router; no undeclared adapter is used."""
        if not isinstance(adapters, Mapping):
            raise TypeError("adapters must be a mapping")
        expected = {item.adapter_name for item in self._providers.values()}
        supplied = set(adapters)
        missing = sorted(expected - supplied)
        unknown = sorted(supplied - expected)
        if missing or unknown:
            details = []
            if missing:
                details.append("missing adapters: " + ", ".join(missing))
            if unknown:
                details.append("undeclared adapters: " + ", ".join(unknown))
            raise ProviderMetadataError("; ".join(details))
        target = router if router is not None else ModelRouter()
        if not isinstance(target, ModelRouter):
            raise TypeError("router must be a ModelRouter")
        for item in self.providers():
            target.register(item, adapters[item.adapter_name])
        return target


__all__ = ["REGISTRY_SCHEMA_VERSION", "RouterRegistry", "RouterRegistrySnapshot"]
