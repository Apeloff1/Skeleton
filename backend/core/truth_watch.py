"""Provenance-gated watch feed for truth lifecycle events.

External alerts are not truth merely because they arrive over a feed. Events are
stored durably and idempotently, but only provenance-verified events may mutate
truth state. Unverified alerts remain visible for operator review.

The feed can also resolve legacy unknown source lineage. A provenance-resolution
event changes ancestry metadata only; it does not itself make any claim true.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from core.file_lease import FileLease


WATCH_VERSION = 1


class TruthWatchIntegrityError(RuntimeError):
    pass


class TruthEventKind(StrEnum):
    SOURCE_RETRACTED = "source_retracted"
    SOURCE_LINEAGE_RESOLVED = "source_lineage_resolved"
    CLAIM_REVERIFY = "claim_reverify"
    CLAIM_CHALLENGED = "claim_challenged"


@dataclass(frozen=True, slots=True)
class TruthWatchEvent:
    sequence: int
    event_id: str
    kind: TruthEventKind
    target: str
    reason: str
    provider: str
    provider_cursor: str
    provenance_verified: bool
    observed_at: str
    applied_at: str = ""
    disposition: str = "pending"
    result_sha256: str = ""
    error: str = ""
    payload_json: str = ""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class TruthWatchFeed:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "truth-watch.json"
        self._lease = FileLease(self.root / ".truth-watch.lock")
        with self._lease.acquire():
            if not self.path.exists(): self._write([], {}, 1)
            else: self._load()

    @staticmethod
    def _checksum(events: list[dict[str, Any]], checkpoints: dict[str, str], next_sequence: int) -> str:
        return _sha({"version": WATCH_VERSION, "events": events, "checkpoints": checkpoints, "next_sequence": next_sequence})

    def _load(self) -> tuple[list[dict[str, Any]], dict[str, str], int]:
        try: env = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise TruthWatchIntegrityError("truth watch unreadable") from exc
        if env.get("version") != WATCH_VERSION: raise TruthWatchIntegrityError("unsupported truth watch version")
        events = env.get("events"); checkpoints = env.get("checkpoints"); next_sequence = env.get("next_sequence"); checksum = env.get("sha256")
        if not isinstance(events, list) or not isinstance(checkpoints, dict) or not isinstance(next_sequence, int) or not isinstance(checksum, str):
            raise TruthWatchIntegrityError("truth watch malformed")
        if not hmac.compare_digest(checksum, self._checksum(events, checkpoints, next_sequence)):
            raise TruthWatchIntegrityError("truth watch checksum mismatch")
        return [dict(x) for x in events if isinstance(x, dict)], {str(k): str(v) for k, v in checkpoints.items()}, next_sequence

    def _write(self, events: list[dict[str, Any]], checkpoints: dict[str, str], next_sequence: int) -> None:
        env = {"version": WATCH_VERSION, "events": events, "checkpoints": checkpoints, "next_sequence": next_sequence,
               "sha256": self._checksum(events, checkpoints, next_sequence)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(env)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    @staticmethod
    def _restore(raw: dict[str, Any]) -> TruthWatchEvent:
        data = dict(raw); data["kind"] = TruthEventKind(data["kind"]); return TruthWatchEvent(**data)

    def ingest(self, *, kind: str | TruthEventKind, target: str, reason: str, provider: str,
               provider_cursor: str = "", provenance_verified: bool = False,
               event_id: str | None = None, observed_at: str | None = None,
               payload: dict[str, Any] | None = None) -> TruthWatchEvent:
        kind = TruthEventKind(kind); target = " ".join(str(target).split()).strip(); provider = str(provider).strip()
        reason = " ".join(str(reason).split()).strip(); payload = dict(payload or {})
        if not target or not provider: raise ValueError("truth watch target and provider are required")
        if kind == TruthEventKind.SOURCE_RETRACTED and not reason: raise ValueError("source retraction requires a reason")
        if kind == TruthEventKind.SOURCE_LINEAGE_RESOLVED and not payload:
            raise ValueError("source lineage resolution requires provenance payload")
        stamp = observed_at or datetime.now(UTC).isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if payload else ""
        identity = event_id or _sha({"kind": kind.value, "target": target, "reason": reason,
                                     "provider": provider, "cursor": provider_cursor, "observed_at": stamp,
                                     "payload": payload_json})[:32]
        with self._lease.acquire():
            events, checkpoints, next_sequence = self._load()
            for raw in events:
                if raw.get("event_id") == identity: return self._restore(raw)
            event = TruthWatchEvent(next_sequence, identity, kind, target, reason[:2000], provider[:300],
                                    str(provider_cursor)[:1000], bool(provenance_verified), stamp,
                                    payload_json=payload_json[:12000])
            events.append({**asdict(event), "kind": event.kind.value}); self._write(events, checkpoints, next_sequence + 1)
            return event

    def pending(self, *, include_unverified: bool = True, limit: int = 100) -> tuple[TruthWatchEvent, ...]:
        if limit < 0 or limit > 1000: raise ValueError("limit must be between 0 and 1000")
        with self._lease.acquire(): events, _, _ = self._load()
        rows = [self._restore(raw) for raw in events if raw.get("disposition") == "pending"]
        if not include_unverified: rows = [row for row in rows if row.provenance_verified]
        return tuple(rows[:limit])

    def apply_pending(self, engine, *, limit: int = 100) -> dict[str, Any]:
        report = {"attempted": 0, "applied": [], "held_unverified": [], "failed": []}
        for event in self.pending(limit=limit):
            report["attempted"] += 1
            if not event.provenance_verified:
                self._finish(event.event_id, "held_unverified", {"reason": "event provenance not verified"})
                report["held_unverified"].append(event.event_id); continue
            try:
                if event.kind == TruthEventKind.SOURCE_RETRACTED:
                    result = engine.retract_source(event.target, event.reason)
                elif event.kind == TruthEventKind.SOURCE_LINEAGE_RESOLVED:
                    try:
                        payload = json.loads(event.payload_json or "{}")
                    except json.JSONDecodeError as exc:
                        raise ValueError("lineage resolution payload is invalid JSON") from exc
                    result = engine.resolve_source_lineage(
                        event.target,
                        source_kind=str(payload.get("source_kind") or "unknown"),
                        locator=str(payload.get("locator") or ""),
                        parent_ids=tuple(payload.get("parent_source_ids") or ()),
                        content_sha256=str(payload.get("content_sha256") or ""),
                    )
                else:
                    # A challenge is a trigger to re-check evidence, not evidence by itself.
                    result = engine.reverify_claim(event.target)
                self._finish(event.event_id, "applied", result, checkpoint=(event.provider, event.provider_cursor))
                report["applied"].append(event.event_id)
            except Exception as exc:
                self._finish(event.event_id, "failed", {"error": f"{type(exc).__name__}: {exc}"})
                report["failed"].append({"event_id": event.event_id, "error": f"{type(exc).__name__}: {exc}"})
        return report

    def _finish(self, event_id: str, disposition: str, result: dict[str, Any], checkpoint: tuple[str, str] | None = None) -> None:
        with self._lease.acquire():
            events, checkpoints, next_sequence = self._load(); found = False
            for raw in events:
                if raw.get("event_id") != event_id: continue
                raw["applied_at"] = datetime.now(UTC).isoformat(); raw["disposition"] = disposition
                raw["result_sha256"] = _sha(result); raw["error"] = str(result.get("error", ""))[:2000]; found = True; break
            if not found: raise KeyError(event_id)
            if checkpoint is not None and checkpoint[1]: checkpoints[checkpoint[0]] = checkpoint[1]
            self._write(events, checkpoints, next_sequence)

    def snapshot(self) -> tuple[TruthWatchEvent, ...]:
        with self._lease.acquire(): events, _, _ = self._load()
        return tuple(self._restore(raw) for raw in events)

    def stats(self) -> dict[str, Any]:
        with self._lease.acquire(): events, checkpoints, next_sequence = self._load()
        counts: dict[str, int] = {}
        for row in events: counts[str(row.get("disposition", "pending"))] = counts.get(str(row.get("disposition", "pending")), 0) + 1
        return {"version": WATCH_VERSION, "events": len(events), "states": counts, "checkpoints": checkpoints,
                "next_sequence": next_sequence, "cross_process_locking": True, "lock_backend": self._lease.backend,
                "sha256": self._checksum(events, checkpoints, next_sequence)}
