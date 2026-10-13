"""SQLite authority for the shadow-weight evidence queue.

A host supplies the database path. Commits are atomic: a transition is copied
into a detached pipeline, recorded and committed before the serving reference
is replaced. Reopening validates every journal link and record identity.
No training, provider call, weight write or deployment is performed here.
"""
from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Callable, TypeVar

from .flgb_training_runtime import digest_json
from .shadow_weight_pipeline import (
    MAX_LEDGER_EVENTS, ShadowEvent, ShadowPolicy, ShadowRecord, ShadowReview,
    ShadowState, ShadowWeightError, ShadowWeightIntake, ShadowWeightPipeline,
    SourceAttestation,
)

_T = TypeVar("_T")
SCHEMA = "skeleton.shadow_weight_sqlite.v1"
_MAX_JSON_BYTES = 256 * 1024
_CREATE = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS shadow_events (
    sequence INTEGER PRIMARY KEY,
    event_digest TEXT NOT NULL UNIQUE,
    event_json TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shadow_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    head_digest TEXT NOT NULL,
    event_count INTEGER NOT NULL,
    schema_version TEXT NOT NULL
);
"""


def _parse_json(data: str) -> dict:
    if len(data.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ShadowWeightError("shadow journal item exceeds byte budget")
    try:
        obj = json.loads(data)
    except (ValueError, TypeError) as exc:
        raise ShadowWeightError("shadow journal contains malformed JSON") from exc
    if not isinstance(obj, dict):
        raise ShadowWeightError("shadow journal record must be an object")
    return obj


def _event_json(event: ShadowEvent) -> str:
    payload = {name: getattr(event, name) for name in (
        "intake_id", "version", "prior_digest", "record_digest",
        "operation", "authority", "evidence_digest", "at_ns",
    )}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _record_json(record: ShadowRecord) -> str:
    return json.dumps(record.to_dict(), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _decode_record(data: str) -> ShadowRecord:
    raw = _parse_json(data)
    if set(raw) != {
        "intake", "state", "version", "review_digest",
        "training_manifest_digest", "consumed_candidate_digest", "last_event_digest",
    }:
        raise ShadowWeightError("shadow record has unsupported fields")
    intake = raw["intake"]
    if not isinstance(intake, dict) or intake.get("schema") != "skeleton.shadow_weight_intake.v1":
        raise ShadowWeightError("invalid shadow intake schema")
    expected_fields = {x.name for x in fields(ShadowWeightIntake)}
    if set(intake) != expected_fields | {"schema"}:
        raise ShadowWeightError("shadow intake has unexpected fields")
    sources = intake["sources"]
    if not isinstance(sources, list):
        raise ShadowWeightError("shadow sources must be an array")
    keys = {field.name for field in fields(SourceAttestation)}
    attested = []
    for raw_source in sources:
        if not isinstance(raw_source, dict) or set(raw_source) != keys:
            raise ShadowWeightError("shadow source has unsupported fields")
        attested.append(SourceAttestation(**raw_source))
    intake = {key: value for key, value in intake.items() if key != "schema"}
    intake["sources"] = tuple(attested)
    shadow_intake = ShadowWeightIntake(**intake)
    try:
        state = ShadowState(raw["state"])
    except ValueError as exc:
        raise ShadowWeightError("invalid persisted shadow state") from exc
    version = raw["version"]
    if type(version) is not int or version < 0:
        raise ShadowWeightError("invalid persisted shadow version")
    for key in ("review_digest", "training_manifest_digest", "consumed_candidate_digest", "last_event_digest"):
        val = raw[key]
        if val is not None and (not isinstance(val, str) or len(val) != 64 or
                                any(c not in "0123456789abcdef" for c in val)):
            raise ShadowWeightError("persisted shadow hash must be sha256")
    return ShadowRecord(
        intake=shadow_intake, state=state, version=version,
        review_digest=raw["review_digest"],
        training_manifest_digest=raw["training_manifest_digest"],
        consumed_candidate_digest=raw["consumed_candidate_digest"],
        last_event_digest=raw["last_event_digest"],
    )


def _decode_event(data: str) -> ShadowEvent:
    raw = _parse_json(data)
    keys = {x.name for x in fields(ShadowEvent)}
    if set(raw) != keys:
        raise ShadowWeightError("shadow event has unsupported fields")
    event = ShadowEvent(**raw)
    if (not isinstance(event.intake_id, str)
            or type(event.version) is not int or event.version < 0
            or type(event.at_ns) is not int or event.at_ns < 0
            or not isinstance(event.operation, str)
            or not isinstance(event.authority, str)):
        raise ShadowWeightError("invalid event identity or timestamp")
    for val in (event.prior_digest, event.record_digest, event.evidence_digest):
        if not isinstance(val, str) or len(val) != 64 or any(
            c not in "0123456789abcdef" for c in val
        ):
            raise ShadowWeightError("invalid journal digest")
    return event


class DurableShadowWeightPipeline:
    """Transactional shadow-intake owner; never grants model promotion.

    The database path and authorization to instantiate this owner are supplied
    by the application. The queue intentionally has no internal worker and no
    timer, so it cannot mutate models without an explicit host call.
    """

    def __init__(self, path: str | Path, *, policy: ShadowPolicy | None = None) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ShadowWeightError("shadow evidence database needs an absolute host path")
        self._lock = RLock()
        self._db = sqlite3.connect(str(self.path), timeout=10,
                                   isolation_level=None, check_same_thread=False)
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_CREATE)
            self.policy = policy or ShadowPolicy()
            self._pipeline = self._restore()
        except BaseException:
            self._db.close()
            raise

    def _restore(self) -> ShadowWeightPipeline:
        queue = ShadowWeightPipeline(policy=self.policy)
        records: dict[str, ShadowRecord] = {}
        prior_head = queue.GENESIS
        count = 0
        rows = self._db.execute(
            "SELECT sequence, event_digest, event_json, record_json "
            "FROM shadow_events ORDER BY sequence"
        )
        for sequence, stored_digest, event_raw, record_raw in rows:
            if count >= MAX_LEDGER_EVENTS or sequence != count:
                raise ShadowWeightError("shadow journal sequence is broken or unbounded")
            event = _decode_event(event_raw)
            record = _decode_record(record_raw)
            previous = records.get(event.intake_id)
            if (event.digest != stored_digest or event.prior_digest != prior_head
                    or event.intake_id != record.identity
                    or record.last_event_digest != event.digest):
                raise ShadowWeightError("shadow journal digest or identity mismatch")
            expected_version = 0 if previous is None else previous.version + 1
            if event.version != expected_version or record.version != expected_version:
                raise ShadowWeightError("shadow journal version chain is broken")
            if previous is not None and record.intake.digest != previous.intake.digest:
                raise ShadowWeightError("shadow intake changed after admission")
            expected_record = record.to_dict()
            expected_record["last_event_digest"] = (
                previous.last_event_digest if previous is not None else None
            )
            if event.record_digest != digest_json(expected_record):
                raise ShadowWeightError("shadow record fingerprint mismatch")
            if previous is None:
                if event.operation != "submit" or record.state is not ShadowState.INBOX:
                    raise ShadowWeightError("shadow journal lacks genesis submission")
            else:
                allowed = {
                    "review": {ShadowState.CORROBORATED, ShadowState.QUARANTINED, ShadowState.REJECTED},
                    "admit_training": {ShadowState.TRAINING_ELIGIBLE},
                    "consume": {ShadowState.CONSUMED},
                    "quarantine": {ShadowState.QUARANTINED},
                }
                if record.state not in allowed.get(event.operation, set()):
                    raise ShadowWeightError("invalid journal lifecycle action")
                if previous.state in (ShadowState.REJECTED, ShadowState.CONSUMED):
                    raise ShadowWeightError("terminal record was rewritten")
            records[event.intake_id] = record
            queue._events.append(event)
            count += 1
            prior_head = event.digest
        meta = self._db.execute(
            "SELECT head_digest, event_count, schema_version "
            "FROM shadow_meta WHERE singleton=1"
        ).fetchone()
        if meta is None:
            if count:
                raise ShadowWeightError("journal data has no authority metadata")
            with self._db:
                self._db.execute(
                    "INSERT INTO shadow_meta VALUES (1, ?, 0, ?)",
                    (queue.GENESIS, SCHEMA),
                )
        elif meta != (prior_head, count, SCHEMA):
            raise ShadowWeightError("shadow journal metadata diverges from evidence chain")
        queue._records = records
        queue._head = prior_head
        return queue

    def _commit(self, transition: Callable[[ShadowWeightPipeline], ShadowRecord]) -> ShadowRecord:
        with self._lock:
            # Reopen snapshot before every mutation so another writer cannot
            # silently branch from a stale chain.
            loaded = self._restore()
            next_record = transition(loaded)
            seq = len(loaded._events) - 1
            event = loaded._events[-1]
            previous = self._pipeline.head_digest
            if event.prior_digest != previous:
                raise ShadowWeightError("shadow writer is stale; refresh before mutation")
            record_raw = _record_json(next_record)
            event_raw = _event_json(event)
            if len(record_raw.encode("utf-8")) > _MAX_JSON_BYTES or len(event_raw.encode("utf-8")) > _MAX_JSON_BYTES:
                raise ShadowWeightError("shadow journal write exceeds item budget")
            try:
                self._db.execute("BEGIN IMMEDIATE")
                actual = self._db.execute(
                    "SELECT head_digest, event_count FROM shadow_meta WHERE singleton=1"
                ).fetchone()
                if actual != (previous, seq):
                    raise ShadowWeightError("concurrent shadow writer changed journal head")
                self._db.execute(
                    "INSERT INTO shadow_events VALUES (?, ?, ?, ?)",
                    (seq, event.digest, event_raw, record_raw),
                )
                self._db.execute(
                    "UPDATE shadow_meta SET head_digest=?, event_count=? WHERE singleton=1",
                    (event.digest, seq + 1),
                )
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            self._pipeline = loaded
            return next_record

    def submit(self, intake: ShadowWeightIntake) -> ShadowRecord:
        if self._pipeline.get(intake.intake_id) is not None:
            prior = self._pipeline.get(intake.intake_id)
            if prior is not None and prior.intake.digest == intake.digest:
                return prior
        return self._commit(lambda queue: queue.submit(intake))

    def review(self, intake_id: str, review: ShadowReview, *, expected_version: int) -> ShadowRecord:
        return self._commit(
            lambda queue: queue.review(intake_id, review, expected_version=expected_version)
        )

    def admit_training(self, intake_id: str, *, expected_version: int,
                       training_manifest_digest: str, training_authority: str,
                       evidence_digest: str, at_ns: int) -> ShadowRecord:
        return self._commit(
            lambda queue: queue.admit_training(
                intake_id, expected_version=expected_version,
                training_manifest_digest=training_manifest_digest,
                training_authority=training_authority,
                evidence_digest=evidence_digest, at_ns=at_ns,
            )
        )

    def consume(self, intake_id: str, *, expected_version: int,
                verified_candidate_digest: str, authority: str, at_ns: int) -> ShadowRecord:
        return self._commit(lambda queue: queue.consume(
            intake_id, expected_version=expected_version,
            verified_candidate_digest=verified_candidate_digest,
            authority=authority, at_ns=at_ns,
        ))

    def quarantine(self, intake_id: str, *, expected_version: int,
                   reason_digest: str, authority: str, at_ns: int) -> ShadowRecord:
        return self._commit(lambda queue: queue.quarantine(
            intake_id, expected_version=expected_version,
            reason_digest=reason_digest, authority=authority, at_ns=at_ns,
        ))

    def get(self, intake_id: str) -> ShadowRecord | None:
        with self._lock:
            return self._pipeline.get(intake_id)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._pipeline.snapshot()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurableShadowWeightPipeline":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = ["DurableShadowWeightPipeline"]
