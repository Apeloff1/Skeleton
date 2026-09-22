"""Fail-closed hybrid persistence helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Dict, Mapping, Optional
import json


class SnapshotError(RuntimeError):
    """Raised when a hybrid snapshot is corrupt or violates locks."""


@dataclass
class HybridPersistence:
    require_pfc_attn_false: bool = True
    require_error_lattice: bool = True

    def dump(self, state: Mapping[str, Any]) -> str:
        self._validate(state)
        blob = json.dumps(state, sort_keys=True, separators=(",", ":"))
        digest = sha256(blob.encode()).hexdigest()
        return json.dumps({"digest": digest, "payload": state}, sort_keys=True)

    def load(self, raw: str) -> dict[str, Any]:
        try:
            envelope = json.loads(raw)
            payload = envelope["payload"]
            digest = envelope["digest"]
        except Exception as exc:  # noqa: BLE001
            raise SnapshotError(f"corrupt envelope: {exc}") from exc
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if sha256(blob.encode()).hexdigest() != digest:
            raise SnapshotError("digest mismatch")
        self._validate(payload)
        return payload

    def _validate(self, state: Mapping[str, Any]) -> None:
        locks = state.get("locks") or {}
        if self.require_pfc_attn_false and locks.get("pfc.attn") not in (False, "false", "False", 0):
            raise SnapshotError("PFC attn lock missing/false required")
        if self.require_error_lattice and not state.get("error_lattice_importable", True):
            raise SnapshotError("error lattice must remain importable")


def demo_state() -> dict[str, Any]:
    return {
        "locks": {"pfc.attn": False, "amalgam.unfitted_kind": "own"},
        "error_lattice_importable": True,
        "ledger_count": 0,
        "pack": "pack_c",
    }
