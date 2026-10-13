"""Portable model-tool manifest for the AI shell surface."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.effects import EffectRegistry
from skeleton.shells.ai.schema import model_response_schema, schema_digest

AI_SHELL_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class AIToolManifest:
    version: int
    tool_catalog_digest: str
    effect_digest: str
    response_schema_digest: str
    tools: tuple[dict[str, object], ...]
    response_schema: dict[str, object]

    def __post_init__(self) -> None:
        if self.version != AI_SHELL_MANIFEST_VERSION:
            raise ValueError("unsupported AI shell manifest version")
        for value in (
            self.tool_catalog_digest,
            self.effect_digest,
            self.response_schema_digest,
        ):
            if len(value) != 64:
                raise ValueError("manifest digests must be SHA-256 hex")

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "tool_catalog_digest": self.tool_catalog_digest,
            "effect_digest": self.effect_digest,
            "response_schema_digest": self.response_schema_digest,
            "tools": [dict(item) for item in self.tools],
            "response_schema": dict(self.response_schema),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


def build_manifest(
    catalog: AIToolCatalog,
    effects: EffectRegistry,
) -> AIToolManifest:
    tools = []
    for card in catalog.cards():
        payload = card.to_dict()
        contract = effects.inspect(card.name)
        payload["effects"] = (
            [] if contract is None else sorted(item.value for item in contract.effects)
        )
        payload["idempotent"] = False if contract is None else contract.idempotent
        payload["reversible"] = False if contract is None else contract.reversible
        payload["human_approval_recommended"] = (
            True if contract is None else contract.human_approval_recommended
        )
        tools.append(payload)
    return AIToolManifest(
        AI_SHELL_MANIFEST_VERSION,
        catalog.digest,
        effects.digest,
        schema_digest(),
        tuple(tools),
        model_response_schema(),
    )
