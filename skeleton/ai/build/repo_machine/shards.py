"""Stable context shards for large-repository machine consumption."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .catalog import build_catalog
from .contracts import contract_map
from .model import RepositoryModel
from .planner import derive_work_candidates


@dataclass(frozen=True, slots=True)
class ContextShard:
    identity: str
    zone: str
    digest: str
    payload: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "zone": self.zone,
            "digest": self.digest,
            "payload": self.payload,
        }


def _digest(value: object) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def build_context_shards(model: RepositoryModel) -> tuple[ContextShard, ...]:
    catalog = build_catalog(model)
    contracts = contract_map(model)
    work = derive_work_candidates(model, limit=256)
    by_zone_work: dict[str, list[dict[str, object]]] = {}
    for item in work:
        by_zone_work.setdefault(item.zone, []).append(item.as_dict())

    shards: list[ContextShard] = []
    for subsystem in model.subsystems:
        capabilities = [
            item.as_dict()
            for item in catalog.by_zone(subsystem.name)
        ]
        payload = {
            "subsystem": subsystem.as_dict(),
            "contract": contracts.get(subsystem.name, {}),
            "capabilities": capabilities[:100],
            "work": by_zone_work.get(subsystem.name, [])[:32],
            "topology": {
                "outbound": [
                    edge.as_dict() for edge in model.edges
                    if edge.source == subsystem.name
                ],
                "inbound": [
                    edge.as_dict() for edge in model.edges
                    if edge.target == subsystem.name
                ],
            },
        }
        shards.append(ContextShard(
            identity=f"zone:{subsystem.name}",
            zone=subsystem.name,
            digest=_digest(payload),
            payload=payload,
        ))
    return tuple(sorted(shards, key=lambda item: item.zone))


def shard_index(model: RepositoryModel) -> dict[str, object]:
    shards = build_context_shards(model)
    return {
        "repository_fingerprint": model.fingerprint,
        "shards": [
            {
                "identity": shard.identity,
                "zone": shard.zone,
                "digest": shard.digest,
            }
            for shard in shards
        ],
    }
