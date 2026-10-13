"""Adaptive competitive-title observatory for original game plans.

The word ENEMY is an internal strategic label for a *title*, NEVER a
characterization of its creators. It does not imply plagiarism or wrongdoing.
Independent post-plan public evidence triggers adversarial delivery obligations,
but no competitor assets, expression, source code or evaluation cases enter
training or the user's original game's identity.

A competitor is not "outdone" by a claimed rating: both measurements must
share a predeclared test protocol, independent evaluator, and source receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from .contracts import QUALITY_AXES, PROTECTED_AXES, canonical_digest, canonical_json

_ID = re.compile(r"^[a-z][a-z0-9_.:-]{1,95}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FEATURE = re.compile(r"^[a-z][a-z0-9_.:-]{2,95}$")
_SCOPES = frozenset({"official_announcement", "official_patch_notes",
                     "official_trailer", "public_demo", "independent_review",
                     "public_technical_article"})
_REVIEW_STATE = frozenset({"reviewed", "unreviewed"})
_SCHEMA = "skeleton.game_builder.competitive_observatory.v1"
_MAX_EVENTS = 4096
_MAX_PAYLOAD = 512000


class CompetitiveError(ValueError):
    """Cannot assert convergence, competence or provenance from unsafe evidence."""


def _ident(value: object, name: str, *, feature: bool=False) -> str:
    pattern = _FEATURE if feature else _ID
    if not isinstance(value,str) or not pattern.fullmatch(value):
        raise CompetitiveError(f"invalid {name}")
    return value


def _hash(value: object, name: str) -> str:
    if not isinstance(value,str) or not _SHA.fullmatch(value):
        raise CompetitiveError(f"invalid {name} SHA256")
    return value


def _time(value: object) -> str:
    if not isinstance(value,str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ",value
    ):
        raise CompetitiveError("canonical UTC seconds required")
    try:
        parsed=datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CompetitiveError("invalid UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise CompetitiveError("noncanonical UTC timestamp")
    return value


def _url(value: object) -> str:
    if not isinstance(value,str) or not 10<=len(value)<=2048:
        raise CompetitiveError("bounded canonical public citation URL required")
    try:
        p=urlsplit(value)
        port=p.port
    except ValueError as exc:
        raise CompetitiveError("invalid public citation URL") from exc
    if (p.scheme!="https" or not p.hostname or p.username or p.password
            or p.fragment or port not in (None,443)
            or not re.fullmatch(r"[A-Za-z0-9.-]+",p.hostname)
            or p.hostname in {"localhost","localhost.localdomain"}
            or p.hostname.endswith((".local",".internal",".test"))
            or any(char.isspace() for char in value)):
        raise CompetitiveError("public HTTPS citation required (not network authority)")
    return value


def _pairs(value: object, field: str, *, min_count=1, max_count=32):
    if (type(value) is not tuple or not min_count<=len(value)<=max_count
            or len(set(value))!=len(value)):
        raise CompetitiveError(f"unique bounded {field} required")
    return value


def _quality(value: object):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100:
        raise CompetitiveError("quality measurements must be finite scores from 0 to 100")
    return float(value)


@dataclass(frozen=True,slots=True)
class DesignFacet:
    feature_id: str
    quality_axis: str
    importance: int
    planned_method_digest: str

    def __post_init__(self):
        _ident(self.feature_id,"original capability",feature=True)
        if self.quality_axis not in QUALITY_AXES:
            raise CompetitiveError("only canonical forge quality axes may be optimized")
        if type(self.importance) is not int or not 1<=self.importance<=5:
            raise CompetitiveError("feature importance must be 1..5")
        _hash(self.planned_method_digest,"prior-original-design")

    def payload(self):
        return dict(feature_id=self.feature_id,quality_axis=self.quality_axis,
                    importance=self.importance,planned_method_digest=self.planned_method_digest)


@dataclass(frozen=True,slots=True)
class PlannedTitle:
    project_id: str
    original_title: str
    registered_at: str
    plan_revision: str
    original_identity_pillars: tuple[str,...]
    distinctive_signature_digest: str
    facets: tuple[DesignFacet,...]

    def __post_init__(self):
        _ident(self.project_id,"original game project")
        if (not isinstance(self.original_title,str)
                or not 1<=len(self.original_title)<=160 or
                self.original_title.strip()!=self.original_title):
            raise CompetitiveError("game title must be bounded original text")
        _time(self.registered_at)
        _hash(self.plan_revision,"original plan revision")
        _hash(self.distinctive_signature_digest,"original identity signature")
        _pairs(self.original_identity_pillars,"protected original identity pillars",
               min_count=2,max_count=12)
        for value in self.original_identity_pillars:
            _ident(value,"original identity pillar",feature=True)
        _pairs(self.facets,"unique planned features",min_count=2,max_count=128)
        if any(not isinstance(f,DesignFacet) for f in self.facets):
            raise CompetitiveError("typed canonical planned game features required")
        if len({f.feature_id for f in self.facets})!=len(self.facets):
            raise CompetitiveError("same planned feature cannot inflate overlap")

    def payload(self):
        return dict(schema="skeleton.game_builder.planned_original_title.v1",
                    project_id=self.project_id,original_title=self.original_title,
                    registered_at=self.registered_at,plan_revision=self.plan_revision,
                    original_identity_pillars=list(self.original_identity_pillars),
                    distinctive_signature_digest=self.distinctive_signature_digest,
                    facets=[f.payload() for f in self.facets])

    @property
    def digest(self):
        return canonical_digest(self.payload())


@dataclass(frozen=True,slots=True)
class CompetitorTitle:
    title_id: str
    public_name: str
    publisher_id: str
    official_url: str
    steam_app_id: int | None = None

    def __post_init__(self):
        _ident(self.title_id,"competitor title")
        _ident(self.publisher_id,"publisher")
        if not isinstance(self.public_name,str) or not 1<=len(self.public_name)<=180 or self.public_name.strip()!=self.public_name:
            raise CompetitiveError("invalid public competing title")
        _url(self.official_url)
        if self.steam_app_id is not None and (
            type(self.steam_app_id) is not int or not 1<=self.steam_app_id<=2_147_483_647
        ):
            raise CompetitiveError("Steam app ID must be positive and bounded")

    def payload(self):
        return dict(title_id=self.title_id,public_name=self.public_name,
                    publisher_id=self.publisher_id,official_url=self.official_url,
                    steam_app_id=self.steam_app_id)


@dataclass(frozen=True,slots=True)
class PublicSignal:
    title_id: str
    signal_id: str
    source_url: str
    source_digest: str
    published_at: str
    observed_at: str
    source_group: str
    signal_kind: str
    reviewed_feature_ids: tuple[str,...]
    review_evidence_digest: str | None
    reviewer_id: str | None

    def __post_init__(self):
        for n in ("title_id","signal_id","source_group"):
            _ident(getattr(self,n),n)
        _url(self.source_url)
        _hash(self.source_digest,"source revision")
        _time(self.published_at);_time(self.observed_at)
        if self.published_at>self.observed_at:
            raise CompetitiveError("future publication time cannot support monitored change")
        if self.signal_kind not in _SCOPES:
            raise CompetitiveError("untrusted content category")
        _pairs(self.reviewed_feature_ids,"reviewed competitor features",
               min_count=0,max_count=64)
        for f in self.reviewed_feature_ids:
            _ident(f,"reviewed rival capability",feature=True)
        if self.review_evidence_digest is None:
            if self.reviewed_feature_ids or self.reviewer_id is not None:
                raise CompetitiveError("unreviewed news may not assert gameplay capabilities")
        else:
            _hash(self.review_evidence_digest,"independent reviewed finding")
            _ident(self.reviewer_id,"reviewer identity")
            if not self.reviewed_feature_ids:
                raise CompetitiveError("review receipts require specific observed features")

    def payload(self):
        return dict(title_id=self.title_id,signal_id=self.signal_id,
                    source_url=self.source_url,source_digest=self.source_digest,
                    published_at=self.published_at,observed_at=self.observed_at,
                    source_group=self.source_group,signal_kind=self.signal_kind,
                    reviewed_feature_ids=list(self.reviewed_feature_ids),
                    review_evidence_digest=self.review_evidence_digest,
                    reviewer_id=self.reviewer_id)


@dataclass(frozen=True,slots=True)
class QualityMeasurement:
    title_id: str
    axis: str
    score: float
    protocol_digest: str
    evaluator_id: str
    evidence_digest: str
    samples: int
    observed_at: str
    independently_reviewed: bool

    def __post_init__(self):
        _ident(self.title_id,"benchmark title")
        if self.axis not in QUALITY_AXES:
            raise CompetitiveError("unknown quality benchmark axis")
        _quality(self.score)
        _hash(self.protocol_digest,"predeclared benchmark protocol")
        _ident(self.evaluator_id,"benchmark evaluator")
        _hash(self.evidence_digest,"benchmark source")
        _time(self.observed_at)
        if type(self.samples) is not int or not 30<=self.samples<=1_000_000:
            raise CompetitiveError("insufficient independently measured samples")
        if type(self.independently_reviewed) is not bool:
            raise CompetitiveError("independent review assertion must be explicit")

    def payload(self):
        return dict(title_id=self.title_id,axis=self.axis,score=self.score,
                    protocol_digest=self.protocol_digest,evaluator_id=self.evaluator_id,
                    evidence_digest=self.evidence_digest,samples=self.samples,
                    observed_at=self.observed_at,
                    independently_reviewed=self.independently_reviewed)


@dataclass(frozen=True,slots=True)
class EnemyPolicy:
    minimum_overlap: float = 0.55
    minimum_unique_matched_features: int = 2
    minimum_independent_groups: int = 2
    margin_points: float = 5.0
    enemy_exit_overlap: float = 0.35

    def __post_init__(self):
        for value in (self.minimum_overlap,self.enemy_exit_overlap):
            if type(value) is not float or not 0<=value<=1:
                raise CompetitiveError("bounded overlap thresholds required")
        if self.enemy_exit_overlap>=self.minimum_overlap:
            raise CompetitiveError("entry threshold must exceed exit threshold")
        if type(self.margin_points) is not float or not 0<self.margin_points<=20:
            raise CompetitiveError("finite quality margin required")
        for n in ("minimum_unique_matched_features","minimum_independent_groups"):
            if type(getattr(self,n)) is not int or not 2<=getattr(self,n)<=12:
                raise CompetitiveError("independence and capability threshold must be 2..12")

    def payload(self):
        return {k:getattr(self,k) for k in self.__dataclass_fields__}


@dataclass(frozen=True,slots=True)
class DeliveryOrder:
    order_id: str
    project_id: str
    rival_title_id: str
    axis: str
    kind: str
    priority: int
    requirement: str
    benchmark_protocol_digest: str | None
    benchmark_evaluator_id: str | None
    minimum_measured_score: float | None
    reference_evidence_digest: str
    protected_identity_digest: str

    def payload(self):
        return {n:getattr(self,n) for n in self.__dataclass_fields__}


@dataclass(frozen=True,slots=True)
class ConvergenceReport:
    project_id: str
    competitor_id: str
    original_plan_digest: str
    signal_root: str
    benchmark_root: str
    status: str
    overlap: float
    independent_evidence_groups: int
    convergent_features: tuple[str,...]
    watch_reasons: tuple[str,...]
    orders: tuple[DeliveryOrder,...]
    previous_report_digest: str | None

    def payload(self):
        body=dict(schema=_SCHEMA,project_id=self.project_id,
                  competitor_id=self.competitor_id,original_plan_digest=self.original_plan_digest,
                  signal_root=self.signal_root,benchmark_root=self.benchmark_root,
                  status=self.status,overlap=self.overlap,
                  independent_evidence_groups=self.independent_evidence_groups,
                  convergent_features=list(self.convergent_features),
                  watch_reasons=list(self.watch_reasons),
                  orders=[o.payload() for o in self.orders],
                  previous_report_digest=self.previous_report_digest,
                  strategic_enemy_label_is_not_an_accusation=True,
                  no_competitor_expression_or_assets_copied=True,
                  protected_original_identity_unchanged=True,
                  competitor_scores_are_not_inferred_from_news=True,
                  automatic_delivery_or_model_promotion=False)
        return {**body,"report_digest":canonical_digest(body)}

    @property
    def digest(self):
        return self.payload()["report_digest"]


def _best_benchmarks(rows: tuple[QualityMeasurement,...],title_id: str):
    seen={}
    for row in rows:
        if row.title_id!=title_id or not row.independently_reviewed:
            continue
        key=(row.axis,row.protocol_digest,row.evaluator_id)
        if key in seen:
            raise CompetitiveError("duplicate independent benchmark assertion")
        seen[key]=row
    return seen


def evaluate_convergence(
    plan: PlannedTitle,rival: CompetitorTitle,
    signals: tuple[PublicSignal,...],benchmarks: tuple[QualityMeasurement,...]=(),
    *,policy: EnemyPolicy=EnemyPolicy(),previous: ConvergenceReport|None=None,
    authorized: bool
)->ConvergenceReport:
    if not authorized:
        raise PermissionError("competitor assessment requires a trusted game operator")
    if (not isinstance(plan,PlannedTitle) or not isinstance(rival,CompetitorTitle)
            or not isinstance(policy,EnemyPolicy) or type(signals) is not tuple
            or type(benchmarks) is not tuple or len(signals)>2048
            or len(benchmarks)>1024
            or any(not isinstance(s,PublicSignal) for s in signals)
            or any(not isinstance(b,QualityMeasurement) for b in benchmarks)):
        raise CompetitiveError("bounded typed monitored evidence required")
    if plan.project_id==rival.title_id:
        raise CompetitiveError("original plan cannot be its own enemy")
    if previous is not None:
        if (not isinstance(previous,ConvergenceReport)
                or previous.project_id!=plan.project_id
                or previous.competitor_id!=rival.title_id
                or previous.original_plan_digest!=plan.digest):
            raise CompetitiveError("cannot recycle unrelated or revised plan history")
    ids=set()
    evidence=set()
    postplan=[]
    for s in signals:
        if s.title_id!=rival.title_id or s.signal_id in ids:
            raise CompetitiveError("signal custody collision or competitor identity mismatch")
        ids.add(s.signal_id)
        # Separate claims in one exact source revision are not independent.
        key=(s.source_group,s.source_digest)
        if key in evidence:
            raise CompetitiveError("duplicate source evidence disguised as separate signals")
        evidence.add(key)
        if s.published_at>=plan.registered_at and s.review_evidence_digest:
            postplan.append(s)
    faceted={f.feature_id:f for f in plan.facets}
    matched=set()
    groups=set()
    for s in postplan:
        relevant=set(s.reviewed_feature_ids)&faceted.keys()
        if relevant:
            matched.update(relevant)
            groups.add(s.source_group)
    matched_weight=sum(faceted[x].importance for x in matched)
    total_weight=sum(f.importance for f in plan.facets)
    overlap=round(matched_weight/total_weight,6)
    reasons=[]
    if len(matched)<policy.minimum_unique_matched_features:
        reasons.append("insufficient_distinct_postplan_capabilities")
    if len(groups)<policy.minimum_independent_groups:
        reasons.append("insufficient_independent_postplan_sources")
    if overlap<policy.minimum_overlap:
        reasons.append("below_material_overlap_threshold")
    verified_enemy=not reasons
    # Hysteresis: a previously substantiated rival requires *lower* overlap
    # to stay on watch as enemy, but NOT a bypass of independent review.
    retained=(previous is not None and previous.status=="enemy"
              and len(matched)>=policy.minimum_unique_matched_features
              and len(groups)>=policy.minimum_independent_groups
              and overlap>=policy.enemy_exit_overlap)
    status="enemy" if verified_enemy or retained else ("watch" if matched else "unconfirmed")
    if retained and not verified_enemy:
        reasons.append("hysteresis_retained_prior_enemy")
    if not signals:
        reasons.append("no_public_competitor_updates")
    source_root=canonical_digest([s.payload() for s in sorted(signals,key=lambda s:s.signal_id)])
    benchmark_root=canonical_digest([b.payload() for b in sorted(
        benchmarks,key=lambda b:(b.title_id,b.axis,b.protocol_digest,b.evaluator_id))])
    orders=[]
    if status=="enemy":
        selected_axes=sorted({faceted[f].quality_axis for f in matched})
        own=_best_benchmarks(benchmarks,plan.project_id)
        theirs=_best_benchmarks(benchmarks,rival.title_id)
        for axis in selected_axes:
            pairs=[]
            for key,x in own.items():
                if key[0]==axis and key in theirs:
                    y=theirs[key]
                    # Exact same independently reviewed measurement protocol and
                    # verifier, *not* self-reported Steam ratings or scraped scores.
                    if (x.observed_at>=plan.registered_at
                            and y.observed_at>=plan.registered_at):
                        pairs.append((key,x,y))
            if len(pairs)>1:
                raise CompetitiveError("ambiguous benchmark protocols would permit cherry-picking")
            if pairs:
                (ax,proto,evaluator),current,rival_measure=pairs[0]
                threshold=round(min(100.,rival_measure.score+policy.margin_points),6)
                if rival_measure.score+policy.margin_points>100:
                    kind="differentiate_and_cap"
                    goal="Competitive maximum prevents a literal exceedance; demonstrate distinctive original player value at the 100-point ceiling."
                else:
                    kind="outperform"
                    goal="Prove a score at or above the fixed target on the SAME independently evaluated protocol with new original-game evidence."
                if current.score>=threshold and kind=="outperform":
                    kind="defend_verified_lead"
                    goal="Preserve the measured lead and guard against regressions across independent player cohorts."
                requirement=f"{goal} Never reduce protected forge quality axes, core identity pillars, rights clearance or platform-fit."
                floor=threshold
                reference=canonical_digest([current.payload(),rival_measure.payload()])
            else:
                kind="commission_comparable_benchmark"
                proto=None
                floor=None
                reference=benchmark_root
                requirement=("Commission paired independently reviewed, preregistered game benchmarks for this axis; no competitor outperformance claim until comparable evidence exists.")
            protocol=pairs[0][0][1] if pairs else None
            priority=min(100,65+round(25*overlap)+(15 if axis in PROTECTED_AXES else 0))
            order_body=dict(project_id=plan.project_id,rival_title_id=rival.title_id,
                            axis=axis,kind=kind,priority=priority,
                            benchmark_protocol_digest=protocol,
                            benchmark_evaluator_id=pairs[0][0][2] if pairs else None,
                            minimum_measured_score=floor,
                            reference_evidence_digest=reference,
                            protected_identity_digest=plan.distinctive_signature_digest)
            oid=canonical_digest(order_body)[:32]
            orders.append(DeliveryOrder(order_id=oid,requirement=requirement,**order_body))
        order_body=dict(project_id=plan.project_id,rival_title_id=rival.title_id,
                        axis="originality",kind="protect_individuality",priority=100,
                        benchmark_protocol_digest=None,benchmark_evaluator_id=None,
                        minimum_measured_score=None,
                        reference_evidence_digest=source_root,
                        protected_identity_digest=plan.distinctive_signature_digest)
        orders.append(DeliveryOrder(
            order_id=canonical_digest(order_body)[:32],**order_body,
            requirement="Retain ALL identity pillars, original design signature, authorial voice and distinctive mechanical intent; create original differentiation, not a substitute clone. Re-run source-rights, similarity and independent originality review."))
    return ConvergenceReport(
        plan.project_id,rival.title_id,plan.digest,source_root,benchmark_root,
        status,overlap,len(groups),tuple(sorted(matched)),
        tuple(sorted(reasons)),tuple(sorted(orders,key=lambda x:(-x.priority,x.axis,x.kind))),
        previous.digest if previous else None,
    )


@dataclass(frozen=True,slots=True)
class DeliveryVerification:
    project_id: str
    plan_digest: str
    protected_identity_digest: str
    independently_reviewed: bool
    protected_axes_passed: bool
    originality_review_passed: bool
    rights_review_passed: bool
    measurements: tuple[QualityMeasurement,...]
    new_gameplay_evidence_digest: str

    def __post_init__(self):
        _ident(self.project_id,"proposed game")
        _hash(self.plan_digest,"unchanged original plan")
        _hash(self.protected_identity_digest,"unchanged original identity")
        _hash(self.new_gameplay_evidence_digest,"new original gameplay")
        for x in ("independently_reviewed","protected_axes_passed",
                  "originality_review_passed","rights_review_passed"):
            if type(getattr(self,x)) is not bool:
                raise CompetitiveError("explicit original game safety attestations required")
        if type(self.measurements) is not tuple or any(not isinstance(m,QualityMeasurement) for m in self.measurements):
            raise CompetitiveError("typed fresh independent measured game quality required")


def verify_delivery(plan: PlannedTitle,report: ConvergenceReport,
                    delivery: DeliveryVerification,*,authorized: bool) -> dict:
    if not authorized:
        raise PermissionError("competitive delivery signoff requires operator review")
    if not isinstance(plan,PlannedTitle) or not isinstance(report,ConvergenceReport) or not isinstance(delivery,DeliveryVerification):
        raise CompetitiveError("complete original-game release validation required")
    if (report.project_id!=plan.project_id or report.original_plan_digest!=plan.digest
            or delivery.project_id!=plan.project_id or delivery.plan_digest!=plan.digest
            or delivery.protected_identity_digest!=plan.distinctive_signature_digest):
        raise CompetitiveError("a competitor cannot rewrite the planned game's individual identity")
    blockers=[]
    for key in ("independently_reviewed","protected_axes_passed",
                "originality_review_passed","rights_review_passed"):
        if not getattr(delivery,key):
            blockers.append(key)
    if not delivery.measurements:
        blockers.append("missing_real_game_measured_results")
    elif any(m.title_id!=plan.project_id or not m.independently_reviewed for m in delivery.measurements):
        blockers.append("untrusted_or_wrong_original_game_measurement")
    for order in report.orders:
        if order.kind in {"outperform","differentiate_and_cap","defend_verified_lead"}:
            matching=[x for x in delivery.measurements if (
                x.title_id==plan.project_id and x.axis==order.axis
                and x.protocol_digest==order.benchmark_protocol_digest
                and x.evaluator_id==order.benchmark_evaluator_id
                and x.independently_reviewed)]
            if (len(matching)!=1 or
                    matching[0].score+1e-9<order.minimum_measured_score):
                blockers.append(f"measured_competitor_target_unmet:{order.axis}")
        elif order.kind=="commission_comparable_benchmark":
            blockers.append(f"independent_competitor_benchmark_missing:{order.axis}")
    return dict(schema="skeleton.game_builder.competitive_delivery_gate.v1",
                plan_digest=plan.digest,report_digest=report.digest,
                new_gameplay_evidence_digest=delivery.new_gameplay_evidence_digest,
                status="competitively_qualified" if not blockers else "blocked",
                blockers=sorted(set(blockers)),
                satisfies_originality_and_rights_only_if_reviewed=True,
                no_actual_publication_or_model_promotion=True)


class CompetitiveLedger:
    """SQLite atomic, full-chain verified audit for original-title watch cycles.

    Expected-head optimistic concurrency prohibits silent older-state writes.
    SHA chain detects changes and dropped interior rows, not deletion of the
    complete database or unanchored last row: callers should anchor head digest
    to independent durable storage.
    """

    def __init__(self,path: str|Path):
        self.path=Path(path)
        if self.path.is_symlink():
            raise CompetitiveError("unsafe competitor ledger symlink")
        self.db=sqlite3.connect(str(path),timeout=10,isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS competitive_ledger(
            seq INTEGER PRIMARY KEY, parent_digest TEXT,
            payload TEXT NOT NULL, digest TEXT NOT NULL)""")

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self,*_):
        self.close()

    def history(self):
        rows=self.db.execute("SELECT seq,parent_digest,payload,digest FROM competitive_ledger ORDER BY seq LIMIT ?",(_MAX_EVENTS+1,)).fetchall()
        if len(rows)>_MAX_EVENTS:
            raise CompetitiveError("competitor audit scan exceeds maximum")
        head=None
        verified=[]
        for count,(seq,parent,raw,digest) in enumerate(rows,1):
            if seq!=count or parent!=head or not isinstance(raw,str) or len(raw)>_MAX_PAYLOAD:
                raise CompetitiveError("competitor audit history broken")
            try:
                def unique(pairs):
                    d={}
                    for k,v in pairs:
                        if k in d:raise CompetitiveError("duplicate audit JSON key")
                        d[k]=v
                    return d
                payload=json.loads(raw,object_pairs_hook=unique,
                                   parse_constant=lambda v: (_ for _ in ()).throw(CompetitiveError("invalid finite JSON")))
            except (ValueError,TypeError) as exc:
                raise CompetitiveError("invalid competitor audit payload") from exc
            if (type(payload) is not dict or raw!=canonical_json(payload)
                    or payload.get("parent_digest")!=parent
                    or payload.get("sequence")!=seq
                    or canonical_digest(payload)!=digest):
                raise CompetitiveError("competitor audit content custody mismatch")
            head=digest
            verified.append(payload)
        return tuple(verified),head

    def append(self,report: ConvergenceReport,*,expected_head: str|None,authorized: bool):
        if not authorized:raise PermissionError("recording competitor findings requires operator")
        if not isinstance(report,ConvergenceReport):
            raise CompetitiveError("only typed analyzed rival reports are admissible")
        if expected_head is not None:_hash(expected_head,"competitor ledger expected head")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            history,head=self.history()
            if expected_head!=head:
                raise CompetitiveError("stale competitive ledger head")
            if len(history)>=_MAX_EVENTS:
                raise CompetitiveError("competitor ledger at capacity")
            body=dict(schema="skeleton.game_builder.competitive_ledger_entry.v1",
                      sequence=len(history)+1,parent_digest=head,
                      project_id=report.project_id,rival_title_id=report.competitor_id,
                      report=report.payload())
            raw=canonical_json(body)
            if len(raw)>_MAX_PAYLOAD:
                raise CompetitiveError("unbounded competitor ledger entry")
            digest=canonical_digest(body)
            self.db.execute("INSERT INTO competitive_ledger VALUES (?,?,?,?)",
                            (body["sequence"],head,raw,digest))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return digest


__all__=["CompetitiveError","DesignFacet","PlannedTitle","CompetitorTitle",
         "PublicSignal","QualityMeasurement","EnemyPolicy","DeliveryOrder",
         "ConvergenceReport","DeliveryVerification","evaluate_convergence",
         "verify_delivery","CompetitiveLedger"]
