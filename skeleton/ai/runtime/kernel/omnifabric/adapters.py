"""Adapters between hex OmniFabric and sibling Fabric shapes.

Keeps backend/zaibatsu Fabric and RS wire formats interoperable without
importing backend sprawl into the hot path. Mapping is structural only.
"""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.kernel.omnifabric.events import FabricEvent, event_from_mapping, event_to_mapping


def from_zaibatsu_dict(data: Mapping[str, Any]) -> FabricEvent:
    """Accept backend.zaibatsu.fabric.FabricEvent asdict() shape."""
    return event_from_mapping(data)


def to_zaibatsu_dict(ev: FabricEvent) -> dict[str, Any]:
    return event_to_mapping(ev)


def from_rs_json(data: Mapping[str, Any]) -> FabricEvent:
    """Accept RS FabricEvent JSON (ts may be RFC3339 string)."""
    from skeleton.kernel.omnifabric.codecs import parse_ts

    payload = dict(data)
    if isinstance(payload.get("ts"), str):
        payload["ts"] = parse_ts(payload["ts"])
    return event_from_mapping(payload)


def to_rs_json(ev: FabricEvent) -> dict[str, Any]:
    from skeleton.kernel.omnifabric.codecs import rfc3339_from_ts

    d = event_to_mapping(ev)
    d["ts"] = rfc3339_from_ts(ev.ts)
    return d


def wire_append_request(body: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize an HTTP append body into OmniFabricService.append kwargs."""
    return {
        "ledger": str(body.get("ledger") or ""),
        "kind": str(body.get("kind") or ""),
        "payload": dict(body.get("payload") or {}),
        "quorum": list(body.get("quorum") or []),
    }
