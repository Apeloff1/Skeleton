"""Governed Dragon acquisition -> shadow sparse weights -> approved routing weights.

Shadow weights are deterministic, compact retrieval hints over reviewed almanac
notes, not learned neural parameters. Live routing sees only separately approved
items. Promotion additionally requires an existing canonical full-chain human-
approved MEMORY_PROMOTION receipt; no source discovery can mint that approval.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import timedelta
from hashlib import sha256
import hmac
import json
import re
import sqlite3

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from skeleton.ai.game_builder.dragon_almanac_weights import WORD
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedKnowledgeStore, KnowledgeBrief,
)
from .dragon_analysis_chains import (
    AnalysisLayer, LayerReceipt, DEFAULT_CHAIN, validate_chain,
)
from .dragon_conditional_automation import (
    SHADOW_RULE, PROMOTION_RULE, VETOES, evaluate_trigger,
)
from .dragon_human_review import DragonHumanReviewLedger
from .dragon_memory_promotion_worker import MemoryPromotionOutput
from .dragon_knowledge_normalization_worker import NormalizedKnowledge, normalization_records_fingerprint
from .dragon_knowledge_manifest import canonical_knowledge_id
from .dragon_adversarial_review_worker import AdversarialReviewOutput, execute_adversarial_review
from .dragon_analysis_execution import LayerDispatch
from .dragon_nest_progression import _id, _instant, _iso
from .dragon_resource_session import HardwareSample, plan_resources

HEX = re.compile(r"[0-9a-f]{64}\Z")
STAGES = ("shadow", "tested", "active", "revoked")
MAX_ITEMS = 2048


def _hash(value: object) -> str:
    return canonical_digest(value)


def _hex(value: str) -> str:
    if not isinstance(value, str) or HEX.fullmatch(value) is None:
        raise ValueError("canonical SHA-256 identity required")
    return value


def _terms(statement: str, mechanic: str) -> tuple[tuple[str, int], ...]:
    weights = Counter(WORD.findall(statement.casefold()))
    for term in WORD.findall(mechanic.casefold()):
        weights[term] += 6
    if not weights or len(weights) > 256:
        raise ValueError("bounded nonempty lexical weight vocabulary required")
    return tuple((key, min(value, 255)) for key, value in sorted(weights.items()))


@dataclass(frozen=True)
class ShadowWeight:
    owner: str
    candidate_id: str
    source_id: str
    source_revision: str
    note_id: str
    knowledge_id: str
    hypothesis_id: str
    ontology_version: str
    probability: float
    probability_semantics: str
    calibration_artifact_fingerprint: str
    evidence_fingerprint: str
    knowledge_root: str
    analysis_digest: str
    adversarial_digest: str
    trigger_digest: str
    terms: tuple[tuple[str, int], ...]
    at: str

    def __post_init__(self) -> None:
        _id(self.owner)
        _id(self.source_id)
        _id(self.note_id)
        for x in (self.candidate_id, self.source_revision, self.knowledge_id,
                  self.calibration_artifact_fingerprint, self.evidence_fingerprint,
                  self.knowledge_root, self.analysis_digest,
                  self.adversarial_digest, self.trigger_digest):
            _hex(x)
        _iso(self.at)
        if (not isinstance(self.hypothesis_id, str)
                or not 1 <= len(self.hypothesis_id) <= 256
                or not isinstance(self.ontology_version, str)
                or not 1 <= len(self.ontology_version) <= 128
                or self.probability_semantics != "empirically_calibrated_probability"
                or type(self.probability) not in (int, float)
                or not 0.9 <= self.probability <= 1.0):
            raise ValueError("shadow candidate requires strongly calibrated normalized knowledge")
        normalized = NormalizedKnowledge(
            self.knowledge_id, self.hypothesis_id, self.ontology_version,
            "supported", self.probability, self.probability_semantics,
            self.calibration_artifact_fingerprint, self.evidence_fingerprint,
            "resolved_support",
        )
        if canonical_knowledge_id(normalized) != self.knowledge_id:
            raise ValueError("shadow normalized evidence identity invalid")
        if (not isinstance(self.terms, tuple)
                or not 1 <= len(self.terms) <= 256
                or any(not isinstance(t, tuple) or len(t) != 2
                       or not isinstance(t[0], str) or not 1 <= len(t[0]) <= 128
                       or type(t[1]) is not int or not 1 <= t[1] <= 255
                       for t in self.terms)
                or self.terms != tuple(sorted(self.terms))
                or len({term for term, _ in self.terms}) != len(self.terms)):
            raise ValueError("invalid deterministic sparse shadow weights")


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    query: str
    expected_source_id: str

    def __post_init__(self) -> None:
        _id(self.case_id)
        if self.expected_source_id != "_abstain":
            _id(self.expected_source_id)
        if (not isinstance(self.query, str) or not 1 <= len(self.query) <= 300
                or not WORD.findall(self.query)):
            raise ValueError("bounded benchmark query required")


@dataclass(frozen=True)
class SealedHoldoutSuite:
    """Evaluation-only canary set, signed by an independent benchmark service.

    The crawler must never receive the issuer's signing key. The seal binds
    questions, expected outcomes, owner, source-root and time before stage.
    """
    owner: str
    knowledge_root: str
    issuer: str
    created_at: str
    expires_at: str
    cases: tuple[BenchmarkCase, ...]
    seal: str

    def __post_init__(self) -> None:
        _id(self.owner)
        _id(self.issuer)
        _hex(self.knowledge_root)
        _hex(self.seal)
        if (not isinstance(self.cases, tuple) or not 5 <= len(self.cases) <= 256
                or any(not isinstance(c, BenchmarkCase) for c in self.cases)):
            raise ValueError("sealed suite must contain five or more typed cases")
        if not _instant(self.created_at) < _instant(self.expires_at):
            raise ValueError("holdout expiry must follow issuance")


def _holdout_body(owner: str, root: str, issuer: str, created: str,
                  expires: str, cases: tuple[BenchmarkCase, ...]) -> str:
    return canonical_json((owner, root, issuer, created, expires,
                           tuple(asdict(case) for case in cases)))


def seal_holdout(
    owner: str, root: str, issuer: str, cases: tuple[BenchmarkCase, ...],
    *, created_at: str, expires_at: str, evaluator_key: bytes,
) -> SealedHoldoutSuite:
    """Call only inside the trusted independent benchmark issuer service."""
    _id(owner)
    _id(issuer)
    _hex(root)
    if not isinstance(evaluator_key, bytes) or len(evaluator_key) < 32:
        raise ValueError("trusted dedicated holdout signing key required")
    created, expires = _iso(created_at), _iso(expires_at)
    if not isinstance(cases, tuple) or len(cases) < 5:
        raise ValueError("independent five-case minimum required")
    raw = _holdout_body(owner, root, issuer, created, expires, cases)
    seal = hmac.new(evaluator_key, raw.encode("utf-8"), sha256).hexdigest()
    return SealedHoldoutSuite(owner, root, issuer, created, expires, cases, seal)


@dataclass(frozen=True)
class BenchmarkVerdict:
    suite_digest: str
    baseline_digest: str
    candidate_id: str
    benchmark_count: int
    before_hits: int
    after_hits: int
    improved: int
    regressed: int
    accepted: bool
    result_digest: str


@dataclass(frozen=True)
class ShadowAudit:
    sequence: int
    at: str
    before: str
    after: str
    action: str
    improvement: str
    previous_digest: str
    digest: str


def _audit(owner: str, candidate: str, number: int, at: str,
           before: str, after: str, action: str, improvement: str,
           prev: str) -> ShadowAudit:
    at = _iso(at)
    if not (improvement.startswith("(") and improvement.endswith(")")
            and len(improvement) <= 350):
        raise ValueError("parenthesized improvement reason required")
    digest = _hash((owner, candidate, number, at, before, after,
                    action, improvement, prev))
    return ShadowAudit(number, at, before, after, action, improvement, prev, digest)


def _compile_postings(
    weights: tuple[ShadowWeight, ...],
) -> dict[str, tuple[tuple[str, int], ...]]:
    """Compile a bounded, deterministic in-memory inverted index once per run.

    Retains the previous integer scoring semantics exactly, including multiple
    approved notes from one source. Runtime route only sees approved entries.
    """
    postings: dict[str, list[tuple[str, int]]] = {}
    if len(weights) > MAX_ITEMS:
        raise ValueError("active sparse routing budget exceeded")
    for weight in weights:
        for term, score in weight.terms:
            postings.setdefault(term, []).append((weight.source_id, score))
    return {term: tuple(sorted(entries))
            for term, entries in sorted(postings.items())}


def _rank_postings(
    postings: dict[str, tuple[tuple[str, int], ...]], query: str,
) -> str | None:
    scores: Counter[str] = Counter()
    for token in sorted(set(WORD.findall(query.casefold()))):
        for source, score in postings.get(token, ()):
            scores[source] += score
    return min(scores, key=lambda source: (-scores[source], source)) if scores else None


def _route(weights: tuple[ShadowWeight, ...], query: str) -> str | None:
    return _rank_postings(_compile_postings(weights), query)


def _benchmark(shadow: ShadowWeight, active: tuple[ShadowWeight, ...],
               suite: SealedHoldoutSuite, *, at: str, key: bytes) -> BenchmarkVerdict:
    if not isinstance(suite, SealedHoldoutSuite):
        raise ValueError("independently sealed holdout is required")
    payload = _holdout_body(
        suite.owner, suite.knowledge_root, suite.issuer,
        suite.created_at, suite.expires_at, suite.cases,
    )
    expected = hmac.new(key, payload.encode("utf-8"), sha256).hexdigest()
    if (not hmac.compare_digest(expected, suite.seal)
            or suite.owner != shadow.owner
            or suite.knowledge_root != shadow.knowledge_root
            or _instant(suite.created_at) > _instant(shadow.at)
            or not _instant(suite.created_at) <= _instant(at) < _instant(suite.expires_at)
            or not 5 <= len(suite.cases) <= 256
            or len({x.case_id for x in suite.cases}) != len(suite.cases)
            or len({x.query.casefold().strip() for x in suite.cases}) != len(suite.cases)):
        raise ValueError("holdout signature, owner, revision or timing invalid")
    cases = suite.cases
    # Canary abstention controls prove that new weights are not matching noise.
    positive = sum(x.expected_source_id == shadow.source_id for x in cases)
    negative = sum(x.expected_source_id == "_abstain" for x in cases)
    if positive < 2 or negative < 2:
        raise ValueError("holdout requires two target and two abstention controls")
    expected_sources = {x.expected_source_id for x in cases}
    if any(x.source_id not in expected_sources for x in active):
        raise ValueError("all existing live sources need regression canaries")
    base = tuple(sorted(active, key=lambda x: x.candidate_id))
    baseline_index = _compile_postings(base)
    proposed_index = _compile_postings((*base, shadow))
    before, after, gained, lost = 0, 0, 0, 0
    for case in cases:
        expected_source = None if case.expected_source_id == "_abstain" else case.expected_source_id
        original = _rank_postings(baseline_index, case.query) == expected_source
        proposed = _rank_postings(proposed_index, case.query) == expected_source
        before += int(original)
        after += int(proposed)
        gained += int(proposed and not original)
        lost += int(original and not proposed)
    baseline = _hash(tuple((x.candidate_id, x.source_revision) for x in base))
    suite_digest = _hash((payload, suite.seal))
    accepted = gained >= 1 and lost == 0 and after > before
    values = (suite_digest, baseline, shadow.candidate_id, len(cases),
              before, after, gained, lost, accepted)
    return BenchmarkVerdict(*values, _hash(values))


class ShadowWeightAutomation:
    """Trusted-worker API only. Does not start threads, crawl or train a model."""

    def __init__(self, db: sqlite3.Connection, library: ReviewedKnowledgeStore,
                 reviews: DragonHumanReviewLedger, *, signing_key: bytes,
                 holdout_key: bytes):
        if (not isinstance(library, ReviewedKnowledgeStore)
                or not isinstance(reviews, DragonHumanReviewLedger)
                or not isinstance(signing_key, bytes) or len(signing_key) < 32
                or not isinstance(holdout_key, bytes) or len(holdout_key) < 32
                or hmac.compare_digest(signing_key, holdout_key)):
            raise ValueError("canonical knowledge, reviewer ledger and separate keys required")
        self.db, self.library, self.reviews, self.key = db, library, reviews, signing_key
        self.holdout_key = holdout_key
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS dragon_shadow_weights (
                owner TEXT NOT NULL, candidate_id TEXT NOT NULL,
                payload TEXT NOT NULL, stage TEXT NOT NULL,
                benchmark TEXT NOT NULL, approval_id TEXT NOT NULL,
                head TEXT NOT NULL, mac TEXT NOT NULL,
                PRIMARY KEY(owner, candidate_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS dragon_shadow_weight_events (
                owner TEXT NOT NULL, candidate_id TEXT NOT NULL, seq INTEGER NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(owner,candidate_id,seq))""")

    def _mac(self, owner: str, cid: str, payload: str, stage: str,
             benchmark: str, approval_id: str, head: str) -> str:
        raw = canonical_json((owner, cid, payload, stage, benchmark, approval_id, head))
        return hmac.new(self.key, raw.encode("utf-8"), sha256).hexdigest()

    def _read(self, owner: str, cid: str):
        row = self.db.execute(
            "SELECT payload,stage,benchmark,approval_id,head,mac "
            "FROM dragon_shadow_weights WHERE owner=? AND candidate_id=?",
            (owner, cid),
        ).fetchone()
        if row is None:
            return None
        raw, stage, benchmark, approval, head, mac = row
        if (not isinstance(raw, str) or len(raw) > 20000
                or stage not in STAGES or not isinstance(benchmark, str)
                or len(benchmark) > 3000 or not isinstance(approval, str)
                or not isinstance(head, str) or len(head) != 64
                or not isinstance(mac, str)
                or not hmac.compare_digest(mac, self._mac(
                    owner, cid, raw, stage, benchmark, approval, head
                ))):
            raise ValueError("shadow row failed signed integrity checks")
        try:
            if raw != canonical_json(json.loads(raw)):
                raise ValueError("noncanonical shadow candidate")
            data = json.loads(raw)
            data["terms"] = tuple(tuple(x) for x in data["terms"])
            shadow = ShadowWeight(**data)
            if shadow.owner != owner or shadow.candidate_id != cid:
                raise ValueError("shadow owner or identity mismatch")
            verdict = None
            if benchmark:
                val = json.loads(benchmark)
                if benchmark != canonical_json(val):
                    raise ValueError("noncanonical benchmark")
                verdict = BenchmarkVerdict(**val)
                fields = (
                    verdict.suite_digest, verdict.baseline_digest, verdict.candidate_id,
                    verdict.benchmark_count, verdict.before_hits,
                    verdict.after_hits, verdict.improved, verdict.regressed, verdict.accepted,
                )
                if (verdict.candidate_id != cid or verdict.result_digest != _hash(fields)
                        or any(not isinstance(x, str) or HEX.fullmatch(x) is None
                               for x in (verdict.suite_digest, verdict.baseline_digest,
                                         verdict.result_digest))
                        or type(verdict.benchmark_count) is not int
                        or not 5 <= verdict.benchmark_count <= 256
                        or any(type(x) is not int or not 0 <= x <= verdict.benchmark_count
                               for x in (verdict.before_hits, verdict.after_hits,
                                         verdict.improved, verdict.regressed))
                        or type(verdict.accepted) is not bool
                        or verdict.after_hits - verdict.before_hits != (
                            verdict.improved - verdict.regressed)
                        or verdict.accepted != (
                            verdict.improved >= 1 and verdict.regressed == 0
                            and verdict.after_hits > verdict.before_hits)):
                    raise ValueError("benchmark receipt mismatch")
            if ((stage in ("tested", "active") and (verdict is None or not verdict.accepted))
                    or (stage == "active" and not _hex(approval))
                    or (stage == "shadow" and (verdict is not None or approval))
                    or (stage == "tested" and approval)):
                raise ValueError("approved weights missing validation")
            rows = self.db.execute(
                "SELECT seq,payload FROM dragon_shadow_weight_events "
                "WHERE owner=? AND candidate_id=? ORDER BY seq", (owner, cid),
            )
            events = []
            parent = "0" * 64
            previous_stage = "absent"
            last_at = shadow.at
            transitions = {
                ("absent", "shadow"),
                ("shadow", "tested"), ("shadow", "revoked"),
                ("tested", "active"), ("tested", "revoked"),
                ("active", "revoked"),
            }
            for expected, (seq, item) in enumerate(rows, 1):
                if expected > 32 or seq != expected or len(item) > 1200:
                    raise ValueError("shadow journal sequence or budget failed")
                data = json.loads(item)
                if item != canonical_json(data):
                    raise ValueError("noncanonical shadow journal entry")
                entry = ShadowAudit(**data)
                control = _audit(owner, cid, seq, entry.at, entry.before,
                                 entry.after, entry.action,
                                 entry.improvement, parent)
                if entry != control:
                    raise ValueError("shadow audit digest chain failed")
                if (entry.action != "transition"
                        or entry.before != previous_stage
                        or (entry.before, entry.after) not in transitions
                        or entry.at < last_at):
                    raise ValueError("shadow audit illegal transition or timestamp rollback")
                events.append(entry)
                previous_stage, last_at = entry.after, entry.at
                parent = entry.digest
            if not events or parent != head or events[-1].after != stage:
                raise ValueError("shadow event history and signed stage disagree")
            return shadow, stage, verdict, approval, tuple(events)
        except (TypeError, KeyError, AttributeError, IndexError,
                ValueError, UnicodeError) as exc:
            raise ValueError("shadow state or history cannot be verified") from exc

    def _write(self, shadow: ShadowWeight, stage: str, verdict: BenchmarkVerdict | None,
               approval_id: str, *, before: str, at: str, improvement: str) -> None:
        owner, cid = shadow.owner, shadow.candidate_id
        existing = self._read(owner, cid)
        if (existing is None and before != "absent"
                or existing is not None and existing[1] != before):
            raise ValueError("shadow transition did not match current stage")
        seq = len(existing[4]) + 1 if existing else 1
        if seq > 32:
            raise ValueError("shadow history needs controlled archival")
        parent = existing[4][-1].digest if existing else "0" * 64
        event = _audit(owner, cid, seq, at, before, stage, "transition", improvement, parent)
        if existing and event.at < existing[4][-1].at:
            raise ValueError("shadow transition cannot be backdated")
        payload = canonical_json(asdict(shadow))
        benchmark = canonical_json(asdict(verdict)) if verdict else ""
        mac = self._mac(owner, cid, payload, stage, benchmark, approval_id, event.digest)
        self.db.execute(
            "INSERT INTO dragon_shadow_weight_events(owner,candidate_id,seq,payload) "
            "VALUES(?,?,?,?)", (owner, cid, seq, canonical_json(asdict(event))),
        )
        if existing is None:
            self.db.execute(
                "INSERT INTO dragon_shadow_weights VALUES(?,?,?,?,?,?,?,?)",
                (owner, cid, payload, stage, benchmark, approval_id, event.digest, mac),
            )
        else:
            result = self.db.execute(
                "UPDATE dragon_shadow_weights SET stage=?, benchmark=?, approval_id=?, "
                "head=?, mac=? WHERE owner=? AND candidate_id=? AND head=?",
                (stage, benchmark, approval_id, event.digest,
                 mac, owner, cid, parent),
            )
            if result.rowcount != 1:
                raise ValueError("concurrent shadow mutation detected")

    def _current(self, shadow: ShadowWeight) -> bool:
        # A new contradictory, retracted or revised canonical source changes
        # the root. Do not keep previously admitted weights live after drift.
        if self.library.snapshot_root(shadow.owner, authorized=True) != shadow.knowledge_root:
            return False
        rows = self.library._rows(shadow.owner)
        for source in rows:
            if (source["source_id"] == shadow.source_id
                    and source["status"] == "active"
                    and "design_reference" in source["allowed_scopes"]
                    and source["revision_digest"] == shadow.source_revision):
                for entry in source["notes"]:
                    note = entry["note"]
                    if (note["note_id"] == shadow.note_id
                            and note["stance"] == "supports"
                            and note["confidence_ppm"] >= 800000
                            and _terms(note["statement"], note["mechanic"]) == shadow.terms):
                        return True
        return False

    def _active(self, owner: str) -> tuple[ShadowWeight, ...]:
        # Verify every owner row before filtering by stage. A forged stage
        # must not make a corrupted active weight silently disappear from audit.
        rows = self.db.execute(
            "SELECT candidate_id FROM dragon_shadow_weights "
            "WHERE owner=? ORDER BY candidate_id", (owner,)
        )
        active = []
        for (cid,) in rows.fetchall():
            current = self._read(owner, cid)
            if current is not None and current[1] == "active" and self._current(current[0]):
                active.append(current[0])
        return tuple(active)

    def stage_shadow(
        self, owner: str, brief: KnowledgeBrief, source_id: str, note_id: str, *,
        normalized_knowledge_id: str, receipts: tuple[LayerReceipt, ...],
        normalized_records: tuple[NormalizedKnowledge, ...],
        adversarial_output: AdversarialReviewOutput,
        adversarial_dispatch: LayerDispatch,
        at: str, idle_since: str, hardware: HardwareSample,
        hardware_now: float, consented: bool, authorized: bool,
        privacy_clear: bool,
    ) -> ShadowWeight:
        """Queue verified evidence as shadow-only when all scrutiny gates pass."""
        if authorized is not True:
            raise PermissionError("trusted owner authority required")
        _id(owner); _id(source_id); _id(note_id)
        _hex(normalized_knowledge_id)
        if not isinstance(brief, KnowledgeBrief) or brief.owner != owner:
            raise ValueError("owner-bound reviewed brief required")
        if not isinstance(receipts, tuple) or len(receipts) != 10:
            raise ValueError("first ten executable scrutiny receipts required")
        verdict = validate_chain(
            receipts, authorized=True, chain=DEFAULT_CHAIN[:10],
        )
        if (not isinstance(normalized_records, tuple)
                or not normalized_records or len(normalized_records) > 1024
                or any(not isinstance(r, NormalizedKnowledge) for r in normalized_records)
                or not isinstance(adversarial_output, AdversarialReviewOutput)
                or not isinstance(adversarial_dispatch, LayerDispatch)
                or adversarial_dispatch.layer is not AnalysisLayer.ADVERSARIAL_REVIEW
                or adversarial_dispatch.input_fingerprints != (
                    receipts[8].output_fingerprint,
                )
                or adversarial_output.receipt != receipts[-1]
                or normalized_knowledge_id not in adversarial_output.surviving_knowledge_ids
                or normalization_records_fingerprint(
                    receipts[8].input_fingerprints, normalized_records,
                ) != receipts[8].output_fingerprint):
            raise ValueError("normalized evidence or adversarial survivors not bound to receipts")
        verified_adversarial = execute_adversarial_review(
            adversarial_dispatch, normalized_records,
            normalization_receipt=receipts[8], authorized=True,
        )
        if verified_adversarial != adversarial_output:
            raise ValueError("adversarial worker findings differ from deterministic replay")
        record = next((r for r in normalized_records
                       if r.knowledge_id == normalized_knowledge_id), None)
        if (record is None or record.knowledge_id != canonical_knowledge_id(record)
                or record.evidence_fingerprint != receipts[7].output_fingerprint
                or record.verdict != "supported"
                or record.contradiction_state != "resolved_support"
                or type(record.probability) not in (int, float)
                or not 0.9 <= record.probability <= 1.0
                or record.probability_semantics != "empirically_calibrated_probability"):
            raise ValueError("unsupported, uncalibrated or unbound normalized knowledge")
        self.library.require_fresh_brief(brief, authorized=True)
        rows = self.library._rows(owner)
        source = next((x for x in rows if x["source_id"] == source_id), None)
        hits = [hit for hit in brief.citations
                if hit.source_id == source_id and hit.note_id == note_id]
        if source is None or len(hits) != 1:
            raise ValueError("exact cited source/note required")
        hit = hits[0]
        note = next((x["note"] for x in source["notes"]
                     if x["note"]["note_id"] == note_id), None)
        if note is None:
            raise ValueError("reviewed note absent")
        now = _instant(at)
        since = _instant(idle_since)
        fresh = _instant(source["observed_at"]) <= now and (
            now - _instant(source["observed_at"])
        ).total_seconds() <= 90 * 86400
        idle = since <= now and (now - since).total_seconds() >= 300
        resources = plan_resources(hardware, now=hardware_now, foreground=False)
        root = self.library.snapshot_root(owner, authorized=True)
        _hex(root)
        original_ids = set()
        for (raw,) in self.db.execute(
            "SELECT payload FROM dragon_shadow_weights WHERE owner=?", (owner,)
        ):
            # Never trust an unsigned row to determine novelty.
            parsed = json.loads(raw)
            prior = self._read(owner, parsed["candidate_id"])
            if prior is not None and prior[1] != "revoked":
                original_ids.add((prior[0].source_id, prior[0].source_revision,
                                  prior[0].note_id))
        total_rows = self.db.execute(
            "SELECT COUNT(*) FROM dragon_shadow_weights WHERE owner=?", (owner,)
        ).fetchone()[0]
        if total_rows > MAX_ITEMS:
            raise ValueError("shadow registry capacity already exceeded")
        if len(original_ids) >= MAX_ITEMS:
            raise ValueError("shadow queue budget exhausted")
        prior_revisions = {rev for sid, rev, _ in original_ids if sid == source_id}
        identity = _hash((
            owner, root, source_id, source["revision_digest"],
            note_id, normalized_knowledge_id,
        ))
        existing_exact = self._read(owner, identity)
        if existing_exact is not None and existing_exact[1] == "revoked":
            raise PermissionError("revoked shadow identity cannot be reinstated")
        newer = bool(prior_revisions - {source["revision_digest"]})
        novel = ((source_id, source["revision_digest"], note_id) not in original_ids
                 or existing_exact is not None)
        blockers = {
            "conflicting": bool(brief.conflicts) or note["stance"] != "supports",
            "retracted": source["status"] != "active",
            "stale": not fresh,
            "privacy_risk": privacy_clear is not True,
            "license_blocked": "design_reference" not in source["allowed_scopes"],
            "benchmark_leakage": False,
            "foreground_active": not idle,
            "budget_exhausted": len(original_ids) >= MAX_ITEMS,
        }
        facts = {
            "task_relevant": note["mechanic"] in brief.query.casefold().split(),
            "adjacent_relevant": hit.relevance > 0,
            "revision_changed": newer,
            "novel": novel,
            "reviewed": note["stance"] == "supports" and note["confidence_ppm"] >= 800000,
            "rights_checked": "design_reference" in source["allowed_scopes"],
            "source_current": fresh,
            "independent_groups": brief.independent_groups >= 2,
            "analysis_passed": verdict.complete,
            "adversarial_passed": receipts[-1].layer is AnalysisLayer.ADVERSARIAL_REVIEW
                                  and receipts[-1].passed,
            "owner_authorized": authorized is True,
            "consented": consented is True,
            "idle": idle,
            "resource_admitted": resources.background_allowed,
            **blockers,
        }
        decision = evaluate_trigger(SHADOW_RULE, facts)
        if not decision.admitted:
            raise PermissionError("shadow admission denied: " + ",".join(decision.reasons))
        if source["revision_digest"] != hit.revision_digest:
            raise ValueError("source changed during scrutiny")
        shadow = ShadowWeight(
            owner, identity, source_id, source["revision_digest"], note_id,
            normalized_knowledge_id, record.hypothesis_id,
            record.ontology_version, record.probability,
            record.probability_semantics,
            record.calibration_artifact_fingerprint, record.evidence_fingerprint,
            root, verdict.fingerprint,
            receipts[-1].output_fingerprint, decision.trace_digest,
            _terms(note["statement"], note["mechanic"]), _iso(at),
        )
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            existing = self._read(owner, identity)
            if existing is not None:
                if existing[0] != shadow:
                    raise ValueError("conflicting shadow acquisition replay")
                return shadow
            if self.db.execute(
                "SELECT COUNT(*) FROM dragon_shadow_weights WHERE owner=?", (owner,)
            ).fetchone()[0] >= MAX_ITEMS:
                raise ValueError("physical shadow registry capacity exhausted")
            self._write(
                shadow, "shadow", None, "", before="absent", at=at,
                improvement="(new scrutinized evidence quarantined as inactive sparse shadow weights)",
            )
        return shadow

    def evaluate(
        self, owner: str, candidate_id: str, suite: SealedHoldoutSuite, *,
        at: str, authorized: bool,
    ) -> BenchmarkVerdict:
        if authorized is not True:
            raise PermissionError("trusted benchmark runner required")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            current = self._read(owner, _hex(candidate_id))
            if current is None or current[1] not in ("shadow", "tested"):
                raise ValueError("only inactive shadow evidence may be tested")
            shadow = current[0]
            if not self._current(shadow):
                raise ValueError("source revision changed or was retracted")
            baseline = self._active(owner)
            result = _benchmark(shadow, baseline, suite, at=at, key=self.holdout_key)
            if not result.accepted:
                # Keep failed experiments quarantined for another independent
                # benchmark. Never represent weak or regressive tests as ready.
                return result
            if current[1] == "tested":
                if result != current[2]:
                    raise ValueError("changed test suite requires new shadow evaluation")
                return result
            self._write(
                shadow, "tested", result, "", before="shadow", at=at,
                improvement=f"(sandbox useful: {result.improved} new top-1 wins; "
                            f"{result.regressed} baseline regressions across "
                            f"{result.benchmark_count} holdout cases)",
            )
            return result

    def promote(
        self, owner: str, candidate_id: str,
        suite: SealedHoldoutSuite, *,
        memory_promotion: MemoryPromotionOutput, review_id: str,
        at: str, authorized: bool,
    ) -> ShadowWeight:
        if authorized is not True:
            raise PermissionError("weight promotion requires trusted authority")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            current = self._read(owner, _hex(candidate_id))
            if current is None or current[1] != "tested" or current[2] is None:
                raise PermissionError("no evaluated shadow candidate")
            shadow, _, prior, _, _ = current
            if not self._current(shadow):
                raise ValueError("reviewed evidence was superseded or retracted")
            if (not isinstance(memory_promotion, MemoryPromotionOutput)
                    or memory_promotion.receipt.layer is not AnalysisLayer.MEMORY_PROMOTION
                    or not memory_promotion.receipt.passed):
                raise PermissionError("canonical memory-promotion receipt required")
            decision = self.reviews.get(owner, _hex(review_id), authorized=True)
            expected_promotion_fingerprint = sha256(json.dumps([
                shadow.knowledge_id, shadow.evidence_fingerprint,
                shadow.calibration_artifact_fingerprint, decision.review_id,
                decision.reviewer_principal_fingerprint,
                shadow.ontology_version,
            ], separators=(",", ":")).encode("utf-8")).hexdigest()
            if (not decision.approved or decision.review_id != review_id
                    or memory_promotion.receipt.input_fingerprints != (review_id,)
                    or memory_promotion.receipt.independent_sources < 2
                    or decision.adversarial_fingerprint != shadow.adversarial_digest
                    or not any(
                        p.knowledge_id == shadow.knowledge_id
                        and p.hypothesis_id == shadow.hypothesis_id
                        and p.ontology_version == shadow.ontology_version
                        and p.probability == shadow.probability
                        and p.human_review_id == review_id
                        and p.promotion_fingerprint == expected_promotion_fingerprint
                        for p in memory_promotion.promoted
                    ) or len({p.knowledge_id for p in memory_promotion.promoted}) != len(memory_promotion.promoted)
                    or memory_promotion.receipt.output_fingerprint != _hash(
                        [vars(item) for item in memory_promotion.promoted]
                    )):
                raise PermissionError("approval/knowledge/adversarial chain mismatch")
            active = self._active(owner)
            current_benchmark = _benchmark(shadow, active, suite, at=at, key=self.holdout_key)
            if current_benchmark != prior:
                raise ValueError("baseline or benchmark drift: rerun evaluation")
            facts = {
                "task_relevant": True, "adjacent_relevant": False,
                "revision_changed": False, "novel": True,
                "reviewed": True, "rights_checked": True, "source_current": True,
                "independent_groups": True, "analysis_passed": True,
                "adversarial_passed": True, "human_approved": True,
                "usefulness_proven": prior.accepted and prior.improved >= 1,
                "regression_free": prior.regressed == 0,
                "owner_authorized": True,
                **{name: False for name in PROMOTION_RULE.but_none},
            }
            admitted = evaluate_trigger(PROMOTION_RULE, facts)
            if not admitted.admitted:
                raise PermissionError("weight promotion blocked: " + ",".join(admitted.reasons))
            self._write(
                shadow, "active", prior, review_id,
                before="tested", at=at,
                improvement="(confirmed useful: adversarially verified, human-approved sparse weights activated with zero benchmark regressions)",
            )
            return shadow

    def revoke(self, owner: str, candidate_id: str, *, at: str,
               reason: str, authorized: bool) -> None:
        if authorized is not True:
            raise PermissionError("trusted rollback required")
        if reason not in ("source_retracted", "performance_regression",
                          "consent_revoked", "integrity_failure", "manual_rollback"):
            raise ValueError("bounded rollback reason required")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            item = self._read(owner, _hex(candidate_id))
            if item is None or item[1] == "revoked":
                return
            shadow, stage, benchmark, approval, _ = item
            self._write(
                shadow, "revoked", benchmark, approval, before=stage, at=at,
                improvement="(rollback: " + reason + "; sparse routing weight disabled)",
            )

    def active_weights(self, owner: str, *, authorized: bool) -> tuple[ShadowWeight, ...]:
        if authorized is not True:
            raise PermissionError("owner authorization required")
        _id(owner)
        return self._active(owner)

    def route(self, owner: str, query: str, *, authorized: bool) -> dict:
        if authorized is not True:
            raise PermissionError("retrieval requires authorization")
        _id(owner)
        if not isinstance(query, str) or not 1 <= len(query) <= 300:
            raise ValueError("bounded retrieval query required")
        active = self._active(owner)
        return {
            "schema": "skeleton.dragon.approved_sparse_routing.v1",
            "source_id": _route(active, query),
            "active_weights": len(active),
            "neural_parameters_modified": False,
            "memory_promotion_authorized": False,
        }

    def registry_health(self, owner: str, *, authorized: bool) -> dict:
        """Verify all signed evidence before reporting activation and staleness.

        This is a point-in-time audit, not a training or crawler instruction.
        """
        if authorized is not True:
            raise PermissionError("owner authorization required")
        _id(owner)
        rows = self.db.execute(
            "SELECT candidate_id FROM dragon_shadow_weights "
            "WHERE owner=? ORDER BY candidate_id", (owner,),
        ).fetchall()
        if len(rows) > MAX_ITEMS:
            raise ValueError("shadow registry hard capacity exceeded")
        status = {stage: 0 for stage in STAGES}
        stale = []
        stale_active = 0
        last_heads = []
        for (cid,) in rows:
            verified = self._read(owner, cid)
            if verified is None:
                raise ValueError("shadow registry index consistency failed")
            shadow, stage, _, _, events = verified
            status[stage] += 1
            last_heads.append((cid, events[-1].digest))
            if stage in ("shadow", "tested", "active") and not self._current(shadow):
                stale.append(cid)
                stale_active += int(stage == "active")
        return {
            "schema": "skeleton.dragon.shadow_registry_health.v1",
            "owner": owner,
            "total": len(rows),
            "stages": status,
            "stale_candidate_ids": tuple(stale),
            "routable_active": status["active"] - stale_active,
            "history_digest": _hash(last_heads),
            "neural_training_authorized": False,
        }


    def history(self, owner: str, candidate_id: str, *,
                authorized: bool) -> tuple[ShadowAudit, ...]:
        if authorized is not True:
            raise PermissionError("owner authorization required")
        item = self._read(owner, _hex(candidate_id))
        return item[4] if item is not None else ()
