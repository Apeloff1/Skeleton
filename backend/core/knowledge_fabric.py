"""Durable multi-surface knowledge fabric for Curiosity.

Every accepted insight is projected into four synchronized surfaces:
- Wiki: explanatory article for retrieval and teaching.
- HOAG: Hypotheses, Observations, Associations and Gaps filing record.
- Newsroom: change/event brief explaining what is newly learned.
- Orientation Room: capability-facing context card used to prime later reasoning.

The fabric is process-safe, append-preserving and integrity-attested. Knowledge is
not treated as model weights: it is durable evidence/context that downstream
reasoning explicitly retrieves and cites by record id.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable

from core.file_lease import FileLease


SCHEMA_VERSION = 1


class KnowledgeIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source: str
    locator: str = ""
    confidence: float = 0.5
    observed_at: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeRecord:
    id: str
    subject: str
    title: str
    summary: str
    claims: tuple[str, ...]
    questions: tuple[str, ...]
    contradictions: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]
    tags: tuple[str, ...]
    confidence: float
    novelty: float
    created_at: str
    parent_prompt_id: str | None
    digest: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text[:80] or "untitled"


def _clamp(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("score must be finite")
    return max(0.0, min(1.0, float(value)))


def _normalize_texts(values: Iterable[str], *, limit: int = 64) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = " ".join(str(raw).split()).strip()
        key = item.casefold()
        if item and key not in seen:
            seen.add(key); out.append(item[:4000])
        if len(out) >= limit:
            break
    return tuple(out)


class KnowledgeFabric:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.wiki = self.root / "wiki"
        self.hoag = self.root / "hoag"
        self.newsroom = self.root / "newsroom"
        self.orientation = self.root / "orientation-room"
        for path in (self.wiki, self.hoag, self.newsroom, self.orientation):
            path.mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.root / "catalog.json"
        self._lease = FileLease(self.root / ".knowledge.lock")
        with self._lease.acquire():
            if not self.catalog_path.exists():
                self._write_catalog({})
            else:
                self._load_catalog()

    @staticmethod
    def _record_payload(record: KnowledgeRecord) -> dict[str, Any]:
        data = asdict(record)
        data.pop("digest", None)
        return data

    def _catalog_digest(self, records: dict[str, dict[str, Any]]) -> str:
        return _digest({"schema_version": SCHEMA_VERSION, "records": records})

    def _load_catalog(self) -> dict[str, dict[str, Any]]:
        try:
            envelope = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise KnowledgeIntegrityError("knowledge catalog unreadable") from exc
        if envelope.get("schema_version") != SCHEMA_VERSION:
            raise KnowledgeIntegrityError("unsupported knowledge catalog schema")
        records = envelope.get("records")
        checksum = envelope.get("sha256")
        if not isinstance(records, dict) or not isinstance(checksum, str):
            raise KnowledgeIntegrityError("knowledge catalog malformed")
        if not hmac.compare_digest(checksum, self._catalog_digest(records)):
            raise KnowledgeIntegrityError("knowledge catalog checksum mismatch")
        return {str(k): dict(v) for k, v in records.items() if isinstance(v, dict)}

    def _write_catalog(self, records: dict[str, dict[str, Any]]) -> None:
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "records": records,
            "sha256": self._catalog_digest(records),
        }
        temp = self.catalog_path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(envelope)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.catalog_path)
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _record_from_dict(raw: dict[str, Any]) -> KnowledgeRecord:
        evidence = tuple(EvidenceRef(**item) for item in raw.get("evidence", ()))
        return KnowledgeRecord(
            id=str(raw["id"]), subject=str(raw["subject"]), title=str(raw["title"]),
            summary=str(raw["summary"]), claims=tuple(raw.get("claims", ())),
            questions=tuple(raw.get("questions", ())), contradictions=tuple(raw.get("contradictions", ())),
            evidence=evidence, tags=tuple(raw.get("tags", ())), confidence=float(raw["confidence"]),
            novelty=float(raw["novelty"]), created_at=str(raw["created_at"]),
            parent_prompt_id=raw.get("parent_prompt_id"), digest=str(raw["digest"]),
        )

    def publish(
        self, *, subject: str, title: str, summary: str,
        claims: Iterable[str] = (), questions: Iterable[str] = (),
        contradictions: Iterable[str] = (), evidence: Iterable[EvidenceRef] = (),
        tags: Iterable[str] = (), confidence: float = 0.5, novelty: float = 0.5,
        parent_prompt_id: str | None = None, created_at: str | None = None,
    ) -> KnowledgeRecord:
        subject = " ".join(subject.split()).strip()
        title = " ".join(title.split()).strip()
        summary = " ".join(summary.split()).strip()
        if not subject or not title or not summary:
            raise ValueError("subject, title and summary are required")
        evidence_tuple = tuple(evidence)
        for item in evidence_tuple:
            _clamp(item.confidence)
        stamp = created_at or datetime.now(UTC).isoformat()
        base = {
            "subject": subject[:300], "title": title[:300], "summary": summary[:12000],
            "claims": _normalize_texts(claims), "questions": _normalize_texts(questions),
            "contradictions": _normalize_texts(contradictions),
            "evidence": tuple(asdict(x) for x in evidence_tuple[:128]),
            "tags": _normalize_texts(tags, limit=32), "confidence": _clamp(confidence),
            "novelty": _clamp(novelty), "created_at": stamp, "parent_prompt_id": parent_prompt_id,
        }
        record_id = _digest(base)[:24]
        payload = {"id": record_id, **base}
        record_digest = _digest(payload)
        record = KnowledgeRecord(
            id=record_id, subject=base["subject"], title=base["title"], summary=base["summary"],
            claims=tuple(base["claims"]), questions=tuple(base["questions"]),
            contradictions=tuple(base["contradictions"]), evidence=evidence_tuple[:128],
            tags=tuple(base["tags"]), confidence=base["confidence"], novelty=base["novelty"],
            created_at=stamp, parent_prompt_id=parent_prompt_id, digest=record_digest,
        )
        with self._lease.acquire():
            catalog = self._load_catalog()
            existing = catalog.get(record.id)
            serialized = asdict(record)
            if existing is not None:
                if existing != serialized:
                    raise KnowledgeIntegrityError("knowledge id collision")
                return self._record_from_dict(existing)
            self._write_surfaces(record)
            catalog[record.id] = serialized
            self._write_catalog(catalog)
        return record

    def _write_surfaces(self, record: KnowledgeRecord) -> None:
        stem = f"{_slug(record.subject)}--{record.id}.md"
        wiki = [f"# {record.title}", "", f"**Subject:** {record.subject}", f"**Confidence:** {record.confidence:.2f}", "", record.summary]
        if record.claims:
            wiki += ["", "## Claims"] + [f"- {x}" for x in record.claims]
        if record.evidence:
            wiki += ["", "## Evidence"] + [f"- {x.source} {x.locator} (confidence {x.confidence:.2f})".strip() for x in record.evidence]
        if record.questions:
            wiki += ["", "## Open questions"] + [f"- {x}" for x in record.questions]
        self._atomic_text(self.wiki / stem, "\n".join(wiki) + "\n")

        hoag = [f"# HOAG — {record.title}", "", "## Hypotheses"] + [f"- {x}" for x in record.claims]
        hoag += ["", "## Observations"] + [f"- {x.source}: {x.locator or 'source evidence'}" for x in record.evidence]
        hoag += ["", "## Associations"] + [f"- #{x}" for x in record.tags]
        hoag += ["", "## Gaps"] + [f"- {x}" for x in (*record.questions, *record.contradictions)]
        self._atomic_text(self.hoag / stem, "\n".join(hoag) + "\n")

        newsroom = [f"# Knowledge News — {record.title}", "", f"**Filed:** {record.created_at}", f"**Novelty:** {record.novelty:.2f}", "", record.summary,
                    "", "## Why this matters", f"This record adds {len(record.claims)} claims, {len(record.evidence)} evidence references and {len(record.questions)} follow-up questions to the knowledge fabric."]
        self._atomic_text(self.newsroom / stem, "\n".join(newsroom) + "\n")

        orientation = [f"# Orientation Card — {record.subject}", "", f"Record: `{record.id}`", f"Confidence: {record.confidence:.2f}", "", "## Working model", record.summary]
        if record.claims:
            orientation += ["", "## Reliable context"] + [f"- {x}" for x in record.claims[:12]]
        if record.contradictions or record.questions:
            orientation += ["", "## Caution / unresolved"] + [f"- {x}" for x in (*record.contradictions, *record.questions)[:12]]
        self._atomic_text(self.orientation / stem, "\n".join(orientation) + "\n")

    @staticmethod
    def _atomic_text(path: Path, content: str) -> None:
        temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        try:
            with temp.open("x", encoding="utf-8") as handle:
                handle.write(content); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def get(self, record_id: str) -> KnowledgeRecord | None:
        with self._lease.acquire():
            raw = self._load_catalog().get(record_id)
        return self._record_from_dict(raw) if raw else None

    def search(self, query: str, *, limit: int = 8) -> tuple[KnowledgeRecord, ...]:
        if limit < 0 or limit > 100:
            raise ValueError("limit must be between 0 and 100")
        terms = {t for t in re.findall(r"[a-z0-9]{2,}", query.casefold())}
        with self._lease.acquire():
            values = [self._record_from_dict(x) for x in self._load_catalog().values()]
        scored: list[tuple[float, KnowledgeRecord]] = []
        for record in values:
            hay = " ".join((record.subject, record.title, record.summary, *record.tags, *record.claims)).casefold()
            overlap = sum(1 for term in terms if term in hay)
            if overlap or not terms:
                score = overlap * 2.0 + record.confidence + record.novelty * 0.5
                scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1].created_at, item[1].id), reverse=True)
        return tuple(record for _, record in scored[:limit])

    def orientation_pack(self, query: str, *, limit: int = 6) -> dict[str, Any]:
        records = self.search(query, limit=limit)
        return {
            "query": query,
            "record_ids": [r.id for r in records],
            "working_context": [r.summary for r in records],
            "claims": [claim for r in records for claim in r.claims[:6]][:24],
            "unresolved": [q for r in records for q in (*r.contradictions, *r.questions)[:4]][:16],
            "confidence_floor": min((r.confidence for r in records), default=0.0),
        }

    def stats(self) -> dict[str, Any]:
        with self._lease.acquire():
            records = self._load_catalog()
        values = list(records.values())
        subjects = {str(x.get("subject", "")).casefold() for x in values}
        return {
            "schema_version": SCHEMA_VERSION,
            "records": len(values),
            "subjects": len(subjects),
            "surface_count": 4,
            "cross_process_locking": True,
            "lock_backend": self._lease.backend,
            "catalog_sha256": self._catalog_digest(records),
        }
