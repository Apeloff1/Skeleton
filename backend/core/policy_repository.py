"""Durable integrity-checked persistence for CharterPolicy.

Policy is encoded canonically, protected by SHA-256, and replaced atomically.
Corruption is fail-closed: callers never receive a partially reconstructed gate.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from core.charter_policy import Charter, CharterPolicy, Edict, GovernanceSnapshot, Rule


class PolicyIntegrityError(RuntimeError):
    pass


class PolicyRepository:
    VERSION = 1

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "charter-policy.json"

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @classmethod
    def _payload(cls, snapshot: GovernanceSnapshot) -> dict[str, Any]:
        return {
            "version": cls.VERSION,
            "charters": [asdict(item) for item in snapshot.charters],
            "edicts": [asdict(item) for item in snapshot.edicts],
        }

    @classmethod
    def _digest(cls, payload: dict[str, Any]) -> str:
        return hashlib.sha256(cls._canonical(payload)).hexdigest()

    def save(self, policy: CharterPolicy) -> str:
        payload = self._payload(policy.snapshot())
        envelope = {"payload": payload, "sha256": self._digest(payload)}
        raw = self._canonical(envelope)
        temp = self.path.with_suffix(".tmp")
        with temp.open("wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)
        return envelope["sha256"]

    def load(self) -> CharterPolicy:
        policy = CharterPolicy()
        if not self.path.exists():
            return policy
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
            payload = envelope["payload"]
            digest = envelope["sha256"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PolicyIntegrityError("policy repository is unreadable") from exc
        if not isinstance(payload, dict) or not isinstance(digest, str):
            raise PolicyIntegrityError("policy repository envelope is malformed")
        if payload.get("version") != self.VERSION:
            raise PolicyIntegrityError("unsupported policy repository version")
        if not hmac.compare_digest(self._digest(payload), digest):
            raise PolicyIntegrityError("policy repository checksum mismatch")
        try:
            snapshot = self._decode_snapshot(payload)
            policy.restore(snapshot)
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyIntegrityError("policy repository state is invalid") from exc
        return policy

    @staticmethod
    def _decode_rule(raw: dict[str, Any]) -> Rule:
        return Rule(
            id=str(raw["id"]),
            action=str(raw["action"]),
            min_weight=int(raw.get("min_weight", 0)),
            requires_quorum=bool(raw.get("requires_quorum", False)),
        )

    @classmethod
    def _decode_snapshot(cls, payload: dict[str, Any]) -> GovernanceSnapshot:
        charters = [
            Charter(
                id=str(raw["id"]),
                domain=str(raw["domain"]),
                rules=[cls._decode_rule(rule) for rule in raw.get("rules", [])],
                ratified_at=str(raw["ratified_at"]),
                amendments=int(raw.get("amendments", 0)),
            )
            for raw in payload.get("charters", [])
        ]
        edicts = [
            Edict(
                id=str(raw["id"]),
                charter_id=str(raw["charter_id"]),
                rule=cls._decode_rule(raw["rule"]),
                proposed_by=str(raw["proposed_by"]),
                proposed_at=str(raw["proposed_at"]),
                in_force=bool(raw.get("in_force", False)),
            )
            for raw in payload.get("edicts", [])
        ]
        return GovernanceSnapshot(charters=charters, edicts=edicts)
