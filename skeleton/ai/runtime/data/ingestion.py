"""Governed ingestion with immutable authority identity and idempotent replay."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Mapping


class IngestionError(ValueError):
    pass


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


@dataclass(frozen=True, slots=True)
class IngestionJob:
    job_id: str
    source_id: str
    source_digest: str
    acquired_at_ns: int
    rights: str
    classification: str
    parser_version: str
    trusted_source: bool

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, str) or not self.job_id:
            raise IngestionError("invalid job identity")
        if not isinstance(self.source_id, str) or not self.source_id:
            raise IngestionError("invalid source identity")
        if not _is_digest(self.source_digest):
            raise IngestionError("invalid source digest")
        if (
            isinstance(self.acquired_at_ns, bool)
            or not isinstance(self.acquired_at_ns, int)
            or self.acquired_at_ns < 0
        ):
            raise IngestionError("invalid acquisition time")
        if any(
            not isinstance(value, str) or not value
            for value in (self.rights, self.classification, self.parser_version)
        ):
            raise IngestionError("incomplete ingestion authority")
        if not isinstance(self.trusted_source, bool):
            raise IngestionError("trusted_source must be boolean")


@dataclass(frozen=True, slots=True)
class IngestedRecord:
    job_id: str
    source_id: str
    source_digest: str
    parser_version: str
    rights: str
    classification: str
    record_digest: str
    value: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    job_id: str
    source_id: str
    source_digest: str
    reason: str


class IngestionEngine:
    def __init__(self) -> None:
        self._jobs: dict[str, IngestionJob] = {}
        self._outcomes: dict[str, IngestedRecord | QuarantineRecord] = {}

    def ingest(
        self,
        job: IngestionJob,
        payload: bytes,
        *,
        parser: Callable[[bytes], Mapping[str, Any]],
    ) -> IngestedRecord | QuarantineRecord:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if not callable(parser):
            raise TypeError("parser must be callable")

        prior_job = self._jobs.get(job.job_id)
        if prior_job is not None:
            if prior_job != job:
                raise IngestionError("job authority cannot be rebound")
            return self._outcomes[job.job_id]

        self._jobs[job.job_id] = job
        if hashlib.sha256(payload).hexdigest() != job.source_digest:
            return self._quarantine(job, "source_digest_mismatch")
        if not job.trusted_source:
            return self._quarantine(job, "untrusted_source")

        try:
            value = parser(payload)
        except Exception:
            return self._quarantine(job, "parser_rejected")
        if not isinstance(value, Mapping):
            return self._quarantine(job, "parser_output_not_mapping")
        try:
            raw = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError):
            return self._quarantine(job, "parser_output_not_canonical")

        outcome = IngestedRecord(
            job.job_id,
            job.source_id,
            job.source_digest,
            job.parser_version,
            job.rights,
            job.classification,
            hashlib.sha256(raw).hexdigest(),
            dict(value),
        )
        self._outcomes[job.job_id] = outcome
        return outcome

    def _quarantine(self, job: IngestionJob, reason: str) -> QuarantineRecord:
        outcome = QuarantineRecord(
            job.job_id,
            job.source_id,
            job.source_digest,
            reason,
        )
        self._outcomes[job.job_id] = outcome
        return outcome
