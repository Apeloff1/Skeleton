"""Resumable, idempotent jobs over stored webhook secrets.

* ``encrypt_plaintext`` - seal legacy plaintext rows (migration of data
  written before encryption at rest existed).
* ``rewrap`` - re-wrap envelopes whose KEK is not the active one (KEK
  rotation). Payload ciphertext is untouched.

Both walk rows in ``secret_id`` order in batches, persist a checkpoint after
each batch (``JobCheckpointStore``), and use compare-and-set writes so a
concurrent writer or a second runner can never clobber a row. Re-running a
finished job is a no-op; a crashed job resumes from its last checkpoint.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Callable, Protocol

from . import envelope
from .envelope import EnvelopeError
from .keys import KeyProvider
from .secret_vault import SecretBlobStore, classify_blob

log = logging.getLogger("skeleton.backend_core.secrets")

JOB_ENCRYPT = "secrets.encrypt_plaintext.v1"
JOB_REWRAP = "secrets.rewrap"


@dataclass(frozen=True)
class Checkpoint:
    job: str
    cursor: str
    done: bool
    updated_at: float


class JobCheckpointStore(Protocol):
    def get(self, job: str) -> Checkpoint | None: ...
    def save(self, cp: Checkpoint) -> None: ...
    def reset(self, job: str) -> None: ...


class MemoryCheckpointStore:
    def __init__(self) -> None:
        self._d: dict[str, Checkpoint] = {}

    def get(self, job: str) -> Checkpoint | None:
        return self._d.get(job)

    def save(self, cp: Checkpoint) -> None:
        self._d[cp.job] = cp

    def reset(self, job: str) -> None:
        self._d.pop(job, None)


@dataclass
class JobReport:
    job: str
    scanned: int = 0
    changed: int = 0
    skipped: int = 0
    conflicts: int = 0
    failed: list[str] = field(default_factory=list)
    batches: int = 0
    done: bool = False
    resumed_from: str = ""

    def as_dict(self) -> dict:
        return {"job": self.job, "scanned": self.scanned, "changed": self.changed,
                "skipped": self.skipped, "conflicts": self.conflicts,
                "failed": list(self.failed), "batches": self.batches, "done": self.done,
                "resumed_from": self.resumed_from or None}


class SecretMigrator:
    def __init__(self, store: SecretBlobStore, provider: KeyProvider, checkpoints: JobCheckpointStore,
                 now: Callable[[], float]) -> None:
        self.store, self.provider, self.checkpoints, self.now = store, provider, checkpoints, now

    @staticmethod
    def _validate_batch_bounds(batch_size: int, max_batches: int | None) -> None:
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be 1..1000")
        if max_batches is not None and (type(max_batches) is not int or not 1 <= max_batches <= 1000):
            raise ValueError("max_batches must be 1..1000 or None")

    def _run(self, job: str, transform, batch_size: int, max_batches: int | None) -> JobReport:
        self._validate_batch_bounds(batch_size, max_batches)
        cp = self.checkpoints.get(job)
        if cp is not None and (
            not isinstance(cp, Checkpoint) or cp.job != job
            or type(cp.cursor) is not str or len(cp.cursor) > 256
            or type(cp.done) is not bool
            or type(cp.updated_at) not in (int, float)
            or not 0 <= cp.updated_at <= 1_000_000_000_000
            or not math.isfinite(cp.updated_at)
        ):
            raise ValueError("invalid secret migration checkpoint")
        report = JobReport(job)
        if cp is not None and cp.done:
            report.done = True
            return report
        cursor = cp.cursor if cp else ""
        report.resumed_from = cursor
        while max_batches is None or report.batches < max_batches:
            rows = self.store.scan(cursor, batch_size)
            if not rows:
                report.done = True
                self.checkpoints.save(Checkpoint(job, cursor, True, self.now()))
                break
            blocked = False
            for row in rows:
                if row.secret_id <= cursor:
                    raise RuntimeError("secret scan cursor did not advance monotonically")
                report.scanned += 1
                aad = envelope.secret_aad(row.tenant_id, row.secret_id)
                try:
                    new = transform(row.blob, aad)
                except EnvelopeError as exc:
                    report.failed.append(row.secret_id)
                    log.error("secret job %s failed for %s: %s", job, row.secret_id, exc)
                    blocked = True
                    break
                if new is None:
                    report.skipped += 1
                elif self.store.compare_and_set(row.secret_id, row.blob, new, envelope.key_id_of(new)):
                    report.changed += 1
                else:
                    report.conflicts += 1
                    blocked = True
                    break
                # Advance only after the row has been durably processed or
                # safely skipped. A failed/conflicting row must be retried.
                cursor = row.secret_id
            report.batches += 1
            self.checkpoints.save(Checkpoint(job, cursor, False, self.now()))
            if blocked:
                return report
        return report

    def encrypt_plaintext(self, batch_size: int = 200, max_batches: int | None = None,
                          force: bool = False) -> JobReport:
        """``force`` re-scans from the start even if a previous run finished
        (e.g. after a legacy writer inserted plaintext rows)."""
        # Validate before force-reset; a rejected invocation must preserve
        # the durable resume checkpoint for the next authorized attempt.
        self._validate_batch_bounds(batch_size, max_batches)
        if force:
            self.checkpoints.reset(JOB_ENCRYPT)
        def transform(blob: bytes, aad: bytes) -> bytes | None:
            kind = classify_blob(blob)
            if kind == "envelope":
                return None
            if kind != "plaintext":
                raise EnvelopeError("row is neither plaintext nor a valid envelope")
            return envelope.seal(self.provider, bytes(blob), aad)
        return self._run(JOB_ENCRYPT, transform, batch_size, max_batches)

    def rewrap(self, batch_size: int = 200, max_batches: int | None = None,
               force: bool = False) -> JobReport:
        self._validate_batch_bounds(batch_size, max_batches)
        target = self.provider.active_key_id()
        job = f"{JOB_REWRAP}:{target}"
        if force:
            self.checkpoints.reset(job)

        def transform(blob: bytes, aad: bytes) -> bytes | None:
            if classify_blob(blob) != "envelope":
                return None  # plaintext is the encrypt job's business
            if envelope.key_id_of(blob) == target:
                return None
            return envelope.rewrap(self.provider, blob, aad, to_key_id=target)
        return self._run(job, transform, batch_size, max_batches)

    def status(self) -> dict:
        counts = self.store.count_by_key()
        active = self.provider.active_key_id()
        plaintext = counts.get("", 0)
        stale = sum(n for k, n in counts.items() if k and k != active)
        return {"active_key_id": active, "plaintext_rows": plaintext, "stale_key_rows": stale,
                "rows_by_key": {k or "plaintext": v for k, v in sorted(counts.items())},
                "encrypt_job": _cp(self.checkpoints.get(JOB_ENCRYPT)),
                "rewrap_job": _cp(self.checkpoints.get(f"{JOB_REWRAP}:{active}"))}


def _cp(cp: Checkpoint | None) -> dict | None:
    return None if cp is None else {"cursor": cp.cursor or None, "done": cp.done, "updated_at": cp.updated_at}


__all__ = ["SecretMigrator", "JobReport", "Checkpoint", "JobCheckpointStore", "MemoryCheckpointStore",
           "JOB_ENCRYPT", "JOB_REWRAP"]
