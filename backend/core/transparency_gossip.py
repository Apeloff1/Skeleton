"""Persistent gossip monitor for transparency-log equivocation detection.

Observers may independently pin tree heads. Different roots for the same log ID and
tree size are cryptographic evidence of a split view. Smaller later tree sizes are
rollback signals. Larger heads are accepted as unproven extensions until a valid
consistency proof connects them to a previously pinned head.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any

from core.file_lease import FileLease
from core.transparency_log import FrontierConsistencyProof, verify_consistency

GOSSIP_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class TransparencyGossipIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GossipObservation:
    log_id: str
    tree_size: int
    root_sha256: str
    source: str
    observed_at: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class TransparencyGossip:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "transparency-gossip.json"
        self._lease = FileLease(self.root / ".transparency-gossip.lock")
        with self._lease.acquire():
            if not self.path.exists(): self._write([], [])
            else: self._load()

    @staticmethod
    def _checksum(observations: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> str:
        return _sha({"version": GOSSIP_VERSION, "observations": observations, "incidents": incidents})

    def _load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try: env = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise TransparencyGossipIntegrityError("gossip ledger unreadable") from exc
        observations = env.get("observations"); incidents = env.get("incidents"); checksum = env.get("sha256")
        if env.get("version") != GOSSIP_VERSION or not isinstance(observations, list) or not isinstance(incidents, list) or not isinstance(checksum, str):
            raise TransparencyGossipIntegrityError("gossip ledger malformed")
        if not hmac.compare_digest(checksum, self._checksum(observations, incidents)):
            raise TransparencyGossipIntegrityError("gossip ledger checksum mismatch")
        return [dict(x) for x in observations if isinstance(x, dict)], [dict(x) for x in incidents if isinstance(x, dict)]

    def _write(self, observations: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> None:
        env = {"version": GOSSIP_VERSION, "observations": observations, "incidents": incidents,
               "sha256": self._checksum(observations, incidents)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(env)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    def observe(self, *, log_id: str, tree_size: int, root_sha256: str, source: str,
                consistency: FrontierConsistencyProof | None = None, observed_at: str | None = None) -> dict[str, Any]:
        log_id = str(log_id).strip(); source = str(source).strip(); root_sha256 = str(root_sha256).lower().strip()
        if not log_id or not source or tree_size < 0 or not _SHA256.fullmatch(root_sha256):
            raise ValueError("invalid gossip observation")
        stamp = observed_at or datetime.now(UTC).isoformat()
        with self._lease.acquire():
            observations, incidents = self._load()
            same_log = [x for x in observations if x.get("log_id") == log_id]
            same_size = [x for x in same_log if int(x.get("tree_size", -1)) == tree_size]
            conflicting = [x for x in same_size if x.get("root_sha256") != root_sha256]
            disposition = "consistent"
            if conflicting:
                disposition = "split_view"
                incident = {"kind": "split_view", "log_id": log_id, "tree_size": tree_size,
                            "roots": sorted({root_sha256, *(str(x.get('root_sha256')) for x in conflicting)}),
                            "sources": sorted({source, *(str(x.get('source')) for x in conflicting)}), "observed_at": stamp}
                if incident not in incidents: incidents.append(incident)
            elif same_log:
                max_size = max(int(x.get("tree_size", 0)) for x in same_log)
                if tree_size < max_size:
                    disposition = "rollback"
                    incident = {"kind": "rollback", "log_id": log_id, "tree_size": tree_size,
                                "max_seen_size": max_size, "root_sha256": root_sha256, "source": source, "observed_at": stamp}
                    incidents.append(incident)
                elif tree_size > max_size:
                    prior = max((x for x in same_log if int(x.get("tree_size", 0)) == max_size), key=lambda x: str(x.get("observed_at", "")))
                    if consistency is not None and verify_consistency(consistency) and consistency.old_size == max_size and consistency.new_size == tree_size and consistency.old_root_sha256 == prior.get("root_sha256") and consistency.new_root_sha256 == root_sha256:
                        disposition = "verified_extension"
                    else:
                        disposition = "unproven_extension"
            row = asdict(GossipObservation(log_id, tree_size, root_sha256, source[:300], stamp))
            if row not in observations: observations.append(row)
            self._write(observations, incidents)
            return {"disposition": disposition, "split_view": disposition == "split_view", "rollback": disposition == "rollback",
                    "incidents": len(incidents), "observation": row}

    def status(self) -> dict[str, Any]:
        with self._lease.acquire(): observations, incidents = self._load()
        split = sum(x.get("kind") == "split_view" for x in incidents); rollback = sum(x.get("kind") == "rollback" for x in incidents)
        return {"version": GOSSIP_VERSION, "observations": len(observations), "incidents": len(incidents),
                "split_views": split, "rollbacks": rollback, "healthy": split == 0 and rollback == 0,
                "cross_process_locking": True, "lock_backend": self._lease.backend,
                "sha256": self._checksum(observations, incidents)}
