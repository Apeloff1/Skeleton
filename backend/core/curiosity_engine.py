"""Curiosity engine: prompt-derived inquiry frontier with durable learning cycles.

Curiosity does not blindly hallucinate knowledge. User prompts create subject
signals; signals compete on novelty, recurrence, unresolved gaps, staleness and
existing coverage. A researcher adapter must return evidence-bearing findings.
Accepted findings are normalized and published through KnowledgeFabric.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import inspect
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Awaitable, Callable, Iterable

from core.file_lease import FileLease
from core.knowledge_fabric import EvidenceRef, KnowledgeFabric, KnowledgeRecord

FRONTIER_VERSION = 1


class CuriosityIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PromptSignal:
    id: str
    subject: str
    prompt_excerpt: str
    keywords: tuple[str, ...]
    observed_at: str
    user_scope: str


@dataclass(slots=True)
class FrontierTopic:
    subject: str
    keywords: list[str]
    prompt_count: int = 0
    unresolved_count: int = 0
    research_count: int = 0
    last_prompt_at: str = ""
    last_researched_at: str = ""
    last_record_id: str | None = None
    priority_bias: float = 0.0


@dataclass(frozen=True, slots=True)
class Inquiry:
    id: str
    subject: str
    questions: tuple[str, ...]
    context_record_ids: tuple[str, ...]
    keywords: tuple[str, ...]
    score: float
    reason: str


Researcher = Callable[[Inquiry, dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]

_STOPWORDS = {"the", "and", "for", "that", "this", "with", "from", "into", "about", "what", "when", "where", "which", "would", "could", "should", "have", "has", "had", "your", "you", "our", "are", "was", "were", "will", "make", "build", "create", "please", "tell", "show", "give", "more", "keep", "continue", "also", "than"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _keywords(text: str, *, limit: int = 12) -> tuple[str, ...]:
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_+.#-]{2,}", text.casefold())
    counts: dict[str, int] = {}
    for token in tokens:
        token = token.strip("._-#")
        if len(token) < 3 or token in _STOPWORDS or token.isdigit():
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts, key=lambda x: (-counts[x], -len(x), x))
    return tuple(ranked[:limit])


def _subject(prompt: str, keys: tuple[str, ...]) -> str:
    cleaned = " ".join(prompt.strip().split())
    return (" / ".join(keys[:5])[:240] if keys else cleaned[:240]) or "general inquiry"


def _parse_time(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class CuriosityEngine:
    def __init__(self, root: str | Path, *, fabric: KnowledgeFabric | None = None) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.fabric = fabric or KnowledgeFabric(self.root / "knowledge")
        self.frontier_path = self.root / "frontier.json"
        self.signal_path = self.root / "prompt-signals.jsonl"
        self._lease = FileLease(self.root / ".curiosity.lock")
        with self._lease.acquire():
            if not self.frontier_path.exists(): self._write_frontier({})
            else: self._load_frontier()

    @staticmethod
    def _frontier_digest(topics: dict[str, dict[str, Any]]) -> str:
        return _sha({"version": FRONTIER_VERSION, "topics": topics})

    def _load_frontier(self) -> dict[str, dict[str, Any]]:
        try: envelope = json.loads(self.frontier_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise CuriosityIntegrityError("curiosity frontier unreadable") from exc
        if envelope.get("version") != FRONTIER_VERSION: raise CuriosityIntegrityError("unsupported curiosity frontier version")
        topics = envelope.get("topics"); digest = envelope.get("sha256")
        if not isinstance(topics, dict) or not isinstance(digest, str): raise CuriosityIntegrityError("curiosity frontier malformed")
        if not hmac.compare_digest(digest, self._frontier_digest(topics)): raise CuriosityIntegrityError("curiosity frontier checksum mismatch")
        return {str(k): dict(v) for k, v in topics.items() if isinstance(v, dict)}

    def _write_frontier(self, topics: dict[str, dict[str, Any]]) -> None:
        envelope = {"version": FRONTIER_VERSION, "topics": topics, "sha256": self._frontier_digest(topics)}
        temp = self.frontier_path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(envelope)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.frontier_path)
        finally:
            temp.unlink(missing_ok=True)

    def _find_signal(self, signal_id: str) -> PromptSignal | None:
        if not self.signal_path.exists(): return None
        try:
            for raw in self.signal_path.read_text(encoding="utf-8").splitlines():
                if not raw.strip(): continue
                data = json.loads(raw)
                if data.get("id") == signal_id:
                    return PromptSignal(str(data["id"]), str(data["subject"]), str(data["prompt_excerpt"]), tuple(data.get("keywords", ())), str(data["observed_at"]), str(data["user_scope"]))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise CuriosityIntegrityError("prompt signal ledger unreadable") from exc
        return None

    def observe_prompt(self, prompt: str, *, user_scope: str = "default", observed_at: str | None = None, signal_key: str | None = None) -> PromptSignal:
        prompt = " ".join(str(prompt).split()).strip()
        if not prompt: raise ValueError("prompt cannot be blank")
        keys = _keywords(prompt); subject = _subject(prompt, keys); stamp = observed_at or datetime.now(UTC).isoformat()
        if signal_key is not None:
            signal_key = str(signal_key).strip()
            if not signal_key: raise ValueError("signal_key cannot be blank")
            signal_id = _sha({"signal_key": signal_key})[:24]
        else:
            signal_id = _sha({"subject": subject, "prompt": prompt[:2000], "at": stamp, "scope": user_scope})[:24]
        with self._lease.acquire():
            existing = self._find_signal(signal_id)
            if existing is not None: return existing
            signal = PromptSignal(signal_id, subject, prompt[:2000], keys, stamp, user_scope[:120])
            topics = self._load_frontier(); raw = topics.get(subject, {})
            topic = FrontierTopic(subject=subject, keywords=list(raw.get("keywords", ())), prompt_count=int(raw.get("prompt_count", 0)), unresolved_count=int(raw.get("unresolved_count", 0)), research_count=int(raw.get("research_count", 0)), last_prompt_at=str(raw.get("last_prompt_at", "")), last_researched_at=str(raw.get("last_researched_at", "")), last_record_id=raw.get("last_record_id"), priority_bias=float(raw.get("priority_bias", 0.0)))
            topic.prompt_count += 1; topic.last_prompt_at = stamp; topic.keywords = list(dict.fromkeys([*keys, *topic.keywords]))[:24]
            topics[subject] = asdict(topic); self._write_frontier(topics)
            with self.signal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(signal), ensure_ascii=False, separators=(",", ":")) + "\n"); handle.flush(); os.fsync(handle.fileno())
            return signal

    def _score_topic(self, topic: FrontierTopic, *, now: float) -> tuple[float, str]:
        existing = self.fabric.search(topic.subject, limit=8)
        coverage = min(1.0, len(existing) / 6.0); mean_conf = sum(r.confidence for r in existing) / len(existing) if existing else 0.0
        unresolved = sum(len(r.questions) + len(r.contradictions) for r in existing) + topic.unresolved_count
        prompt_strength = min(1.0, math.log2(topic.prompt_count + 1) / 3.0); novelty = 1.0 - min(1.0, coverage * max(mean_conf, 0.25))
        last = _parse_time(topic.last_researched_at); staleness = 1.0 if not last else min(1.0, max(0.0, now - last) / (7 * 86400.0))
        gap_pressure = min(1.0, unresolved / 8.0); fatigue = min(0.6, topic.research_count * 0.08)
        score = 0.30 * prompt_strength + 0.28 * novelty + 0.22 * gap_pressure + 0.20 * staleness + topic.priority_bias - fatigue
        return max(0.0, round(score, 6)), f"prompt={prompt_strength:.2f};novelty={novelty:.2f};gaps={gap_pressure:.2f};stale={staleness:.2f};fatigue={fatigue:.2f}"

    def frontier(self, *, limit: int = 20, now: float | None = None) -> tuple[tuple[FrontierTopic, float, str], ...]:
        if limit < 0 or limit > 500: raise ValueError("limit must be between 0 and 500")
        now = time.time() if now is None else float(now)
        with self._lease.acquire(): raw_topics = self._load_frontier()
        ranked = []
        for raw in raw_topics.values():
            topic = FrontierTopic(**raw); score, reason = self._score_topic(topic, now=now); ranked.append((topic, score, reason))
        ranked.sort(key=lambda item: (item[1], item[0].prompt_count, item[0].subject), reverse=True)
        return tuple(ranked[:limit])

    def next_inquiry(self, *, minimum_score: float = 0.18, now: float | None = None) -> Inquiry | None:
        ranked = self.frontier(limit=1, now=now)
        if not ranked: return None
        topic, score, reason = ranked[0]
        if score < minimum_score: return None
        context = self.fabric.search(topic.subject, limit=6); unresolved = [q for record in context for q in (*record.contradictions, *record.questions)]
        questions: list[str] = []
        for question in unresolved:
            if question not in questions: questions.append(question)
        for question in (f"What are the foundational concepts and strongest evidence for {topic.subject}?", f"What are the most important unresolved disagreements or failure modes in {topic.subject}?", f"What has changed recently or is commonly misunderstood about {topic.subject}?", f"Which adjacent concepts would most improve practical reasoning about {topic.subject}?"):
            if question not in questions: questions.append(question)
        inquiry_id = _sha({"subject": topic.subject, "questions": questions[:8], "records": [r.id for r in context]})[:24]
        return Inquiry(inquiry_id, topic.subject, tuple(questions[:8]), tuple(r.id for r in context), tuple(topic.keywords), score, reason)

    @staticmethod
    def _evidence(raw: Iterable[dict[str, Any]]) -> tuple[EvidenceRef, ...]:
        out = []
        for item in raw:
            if not isinstance(item, dict) or not str(item.get("source", "")).strip(): continue
            conf = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
            out.append(EvidenceRef(str(item["source"])[:1000], str(item.get("locator", ""))[:2000], conf, str(item.get("observed_at", ""))[:100]))
        return tuple(out[:128])

    def accept_finding(self, inquiry: Inquiry, finding: dict[str, Any]) -> KnowledgeRecord:
        if not isinstance(finding, dict): raise ValueError("research finding must be an object")
        summary = " ".join(str(finding.get("summary", "")).split()).strip()
        if not summary: raise ValueError("research finding requires a summary")
        evidence = self._evidence(finding.get("evidence") or ()); claims = tuple(str(x) for x in (finding.get("claims") or ()))
        requested_conf = max(0.0, min(1.0, float(finding.get("confidence", 0.5)))); confidence = min(requested_conf, 0.45) if claims and not evidence else requested_conf
        previous = self.fabric.search(inquiry.subject, limit=12); previous_claims = {c.casefold() for r in previous for c in r.claims}; novel_claims = sum(1 for claim in claims if claim.casefold() not in previous_claims)
        novelty = min(1.0, (novel_claims + len(finding.get("questions") or ())) / max(1, len(claims) + 3))
        record = self.fabric.publish(subject=inquiry.subject, title=str(finding.get("title") or f"Curiosity brief: {inquiry.subject}"), summary=summary, claims=claims, questions=tuple(str(x) for x in (finding.get("questions") or ())), contradictions=tuple(str(x) for x in (finding.get("contradictions") or ())), evidence=evidence, tags=tuple(inquiry.keywords) + tuple(str(x) for x in (finding.get("tags") or ())), confidence=confidence, novelty=novelty, parent_prompt_id=inquiry.id)
        with self._lease.acquire():
            topics = self._load_frontier(); raw = topics.get(inquiry.subject)
            if raw is not None:
                raw["research_count"] = int(raw.get("research_count", 0)) + 1; raw["last_researched_at"] = datetime.now(UTC).isoformat(); raw["last_record_id"] = record.id; raw["unresolved_count"] = len(record.questions) + len(record.contradictions); topics[inquiry.subject] = raw; self._write_frontier(topics)
        return record

    async def run_once(self, researcher: Researcher, *, minimum_score: float = 0.18) -> dict[str, Any]:
        inquiry = self.next_inquiry(minimum_score=minimum_score)
        if inquiry is None: return {"status": "idle", "reason": "no inquiry above curiosity threshold"}
        context = self.fabric.orientation_pack(inquiry.subject, limit=8); result = researcher(inquiry, context)
        if inspect.isawaitable(result): result = await result
        record = self.accept_finding(inquiry, result)
        return {"status": "learned", "inquiry_id": inquiry.id, "subject": inquiry.subject, "record_id": record.id, "digest": record.digest, "score": inquiry.score, "surfaces": ("wiki", "hoag", "newsroom", "orientation-room")}

    def boost(self, subject: str, delta: float = 0.15) -> bool:
        with self._lease.acquire():
            topics = self._load_frontier(); raw = topics.get(subject)
            if raw is None: return False
            raw["priority_bias"] = max(-0.5, min(0.75, float(raw.get("priority_bias", 0.0)) + delta)); topics[subject] = raw; self._write_frontier(topics); return True

    def stats(self) -> dict[str, Any]:
        with self._lease.acquire(): topics = self._load_frontier()
        return {"frontier_version": FRONTIER_VERSION, "topics": len(topics), "prompt_signals": sum(int(x.get("prompt_count", 0)) for x in topics.values()), "research_cycles": sum(int(x.get("research_count", 0)) for x in topics.values()), "frontier_sha256": self._frontier_digest(topics), "knowledge": self.fabric.stats(), "cross_process_locking": True, "lock_backend": self._lease.backend}
