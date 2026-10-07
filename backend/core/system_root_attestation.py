"""Hierarchical attestation for the converged product control plane.

Each independent control-plane component is canonically hashed, then the sorted
component digests are folded into one root. This is intentionally Merkle-like:
operators can compare one root across processes/releases and still identify the
specific component whose evidence changed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class RootAttestation:
    schema_version: int
    components: tuple[tuple[str, str], ...]
    root_sha256: str

    def component_map(self) -> dict[str, str]:
        return dict(self.components)


def build_root_attestation(components: Mapping[str, Any]) -> RootAttestation:
    if not components:
        raise ValueError("at least one attestation component is required")
    normalized: list[tuple[str, str]] = []
    for name, value in components.items():
        key = str(name).strip()
        if not key:
            raise ValueError("attestation component names cannot be blank")
        normalized.append((key, _digest(value)))
    normalized.sort(key=lambda item: item[0])
    root_payload = {
        "schema_version": 1,
        "components": [{"name": name, "sha256": digest} for name, digest in normalized],
    }
    return RootAttestation(
        schema_version=1,
        components=tuple(normalized),
        root_sha256=_digest(root_payload),
    )


def verify_root_attestation(attestation: RootAttestation, components: Mapping[str, Any]) -> bool:
    try:
        rebuilt = build_root_attestation(components)
    except (TypeError, ValueError):
        return False
    return rebuilt == attestation


def diff_root_attestations(left: RootAttestation, right: RootAttestation) -> dict[str, tuple[str | None, str | None]]:
    before = left.component_map()
    after = right.component_map()
    names = sorted(set(before) | set(after))
    return {
        name: (before.get(name), after.get(name))
        for name in names
        if before.get(name) != after.get(name)
    }
