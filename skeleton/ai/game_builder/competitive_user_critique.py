"""Constructive self-critique of the CURRENT original project, all 102 facets.

A title being watched is not evidence that its current project build exists or
passes any facet. Bind a project snapshot and actual signed game scores before
drawing project-specific conclusions. Unknown equals a research / test task.
Never treat a competitor's weak point as a defect of the player's game.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hmac

from .contracts import canonical_digest
from .competitive_title_radar import PlannedOriginalTitle,ThreatRadarError,_id,_date,_sha
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .competitive_deep_service import EnemyDeepDossier
from .competitive_deep_analysis import FACETS, ScriptedProbe,FacetMeasurement,FacetVerdict
from .competitive_counterproposals import REMEDIATIONS


@dataclass(frozen=True,slots=True)
class UserGameSnapshot:
    original_id: str
    frozen_design_digest: str
    current_build_digest: str
    project_tree_digest: str
    platform: str
    captured_at: str
    state: str = "instrumented_build"

    def __post_init__(self):
        _id(self.original_id,"original project ID")
        for field in ("frozen_design_digest","current_build_digest","project_tree_digest"):
            _sha(getattr(self,field),field)
        _id(self.platform,"project platform")
        _date(self.captured_at)
        if self.state not in {"instrumented_build","source_only","prototype"}:
            raise ThreatRadarError("named project state is required")

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.user_project_snapshot.v1",
                    original_id=self.original_id,
                    frozen_design_digest=self.frozen_design_digest,
                    current_build_digest=self.current_build_digest,
                    project_tree_digest=self.project_tree_digest,
                    platform=self.platform,captured_at=self.captured_at,
                    state=self.state,
                    source_tree_claim_not_a_gameplay_score=True)


@dataclass(frozen=True,slots=True)
class ReviewedUserProjectEvidence:
    snapshot_digest: str
    original_measurement_digests: tuple[str,...]
    independent_reviewer_id: str
    review_time: str
    signature: str

    def __post_init__(self):
        _sha(self.snapshot_digest,"project snapshot")
        if (type(self.original_measurement_digests) is not tuple or
                len(self.original_measurement_digests)>1024 or
                tuple(sorted(set(self.original_measurement_digests)))!=self.original_measurement_digests):
            raise ThreatRadarError("unique sorted measurement receipts required")
        for d in self.original_measurement_digests:
            _sha(d,"project measurement")
        _id(self.independent_reviewer_id,"project reviewer")
        _date(self.review_time)
        _sha(self.signature,"review signature")

    def body(self):
        return dict(schema="skeleton.game_builder.user_project_evidence.v1",
                    snapshot_digest=self.snapshot_digest,
                    original_measurement_digests=list(self.original_measurement_digests),
                    independent_reviewer_id=self.independent_reviewer_id,
                    review_time=self.review_time)

    def payload(self):
        return dict(self.body(),signature=self.signature)


def sign_project_evidence(evidence: ReviewedUserProjectEvidence,
                          judge: TrustedCompetitionJudge):
    if (not isinstance(evidence,ReviewedUserProjectEvidence)
            or not isinstance(judge,TrustedCompetitionJudge)
            or judge.judge_id!=evidence.independent_reviewer_id):
        raise ThreatRadarError("project evidence reviewer key mismatch")
    return replace(evidence,signature=_mac(evidence.body(),judge.key))


@dataclass(frozen=True,slots=True)
class ProjectCriticism:
    facet: str
    domain: str
    status: str
    observed_original_lower_bp: int|None
    rival_upper_bp: int|None
    criticism: str
    corrective_action: str
    reproducible_test: str
    project_identity_pillars: tuple[str,...]
    evidence_digest: str
    priority: int
    blocked_reason: str|None

    def payload(self):
        return dict(schema="skeleton.game_builder.constructive_critique.v1",
                    facet=self.facet,domain=self.domain,status=self.status,
                    observed_original_lower_bp=self.observed_original_lower_bp,
                    rival_upper_bp=self.rival_upper_bp,
                    criticism=self.criticism,corrective_action=self.corrective_action,
                    reproducible_test=self.reproducible_test,
                    project_identity_pillars=list(self.project_identity_pillars),
                    evidence_digest=self.evidence_digest,priority=self.priority,
                    blocked_reason=self.blocked_reason,
                    not_an_automatic_build_edit=True,
                    no_competitor_expression_copied=True)


@dataclass(frozen=True,slots=True)
class CurrentProjectCritique:
    snapshot_digest: str
    original_id: str
    rival_id: str
    all_facet_count: int
    criticisms: tuple[ProjectCriticism,...]
    missing_live_measurements: int
    actual_build_measurement_qualified: bool

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.current_project_critique.v1",
                    snapshot_digest=self.snapshot_digest,
                    original_id=self.original_id,rival_id=self.rival_id,
                    all_facet_count=self.all_facet_count,
                    criticisms=[x.payload() for x in self.criticisms],
                    missing_live_measurements=self.missing_live_measurements,
                    actual_build_measurement_qualified=self.actual_build_measurement_qualified,
                    genuine_gameplay_quality_not_inferred_from_file_count=True)


def critique_current_user_game(
    original: PlannedOriginalTitle,
    snapshot: UserGameSnapshot,
    dossier: EnemyDeepDossier,
    original_measurements: tuple[FacetMeasurement,...], *,
    evidence: ReviewedUserProjectEvidence|None,
    trusted_reviewer: TrustedCompetitionJudge|None,
    as_of: str,authorized: bool,
)->CurrentProjectCritique:
    if not authorized:
        raise PermissionError("current project critique requires explicit studio authority")
    _date(as_of)
    if (not isinstance(original,PlannedOriginalTitle)
            or not isinstance(snapshot,UserGameSnapshot)
            or not isinstance(dossier,EnemyDeepDossier)
            or snapshot.original_id!=original.title_id
            or snapshot.frozen_design_digest!=original.design_digest
            or snapshot.platform not in original.platforms
            or dossier.original_id!=original.title_id
            or dossier.platform!=snapshot.platform
            or len(dossier.analysis_scripts)!=sum(map(len,FACETS.values()))
            or len(dossier.facet_verdicts)!=len(dossier.analysis_scripts)
            or type(original_measurements) is not tuple
            or len(original_measurements)>1024
            or any(not isinstance(x,FacetMeasurement) for x in original_measurements)):
        raise ThreatRadarError("actual project snapshot and untruncated matched research required")
    if _date(snapshot.captured_at)>_date(as_of):
        raise ThreatRadarError("future project build cannot be evaluated")
    measurements={canonical_digest(row.payload()) for row in original_measurements}
    if len(measurements)!=len(original_measurements):
        raise ThreatRadarError("duplicate project receipts in signed evidence")
    trusted=False
    if evidence is not None:
        if (not isinstance(evidence,ReviewedUserProjectEvidence)
                or not isinstance(trusted_reviewer,TrustedCompetitionJudge)
                or evidence.independent_reviewer_id!=trusted_reviewer.judge_id
                or evidence.snapshot_digest!=snapshot.digest
                or evidence.original_measurement_digests!=tuple(sorted(measurements))
                or not hmac.compare_digest(
                    evidence.signature,_mac(evidence.body(),trusted_reviewer.key))
                or _date(evidence.review_time)>_date(as_of)):
            raise ThreatRadarError("current original-game build lacks exact signed source and replay custody")
        trusted=True
    elif original_measurements:
        raise ThreatRadarError("cannot score live user project from unbound external measurements")
    by_facet={x.facet:x for x in dossier.facet_verdicts}
    samples_by_script={}
    for row in original_measurements:
        if row.subject_id!=original.title_id:
            raise ThreatRadarError("rival measurements cannot be submitted as user's game")
        samples_by_script.setdefault(row.script_digest,[]).append(row)
    if set(samples_by_script)-{s.digest for s in dossier.analysis_scripts}:
        raise ThreatRadarError("unreviewed script injected into project critique")
    results=[]
    for script in dossier.analysis_scripts:
        verdict=by_facet.get(script.facet)
        if verdict is None or verdict.script_digest!=script.digest:
            raise ThreatRadarError("missing or mismatched competitor analysis")
        rows=samples_by_script.get(script.digest,[])
        # This layer does not cryptographically attest individual rows; that
        # is the job of the earlier scorer. Both full run and exact set of
        # result receipts must be bound and operator-review signed here.
        has_data=(trusted and snapshot.state=="instrumented_build"
                  and len({r.evaluator_id for r in rows})>=2
                  and verdict.status!="insufficient_evidence"
                  and verdict.original_conservative_lower_bp is not None)
        if not has_data:
            status="unmeasured"
            message="No full-coverage verified replay comparison for this actual project build."
            reason="collect_two_independent_current_build_replays_and_signature"
        elif verdict.gap_to_outperform_bp and verdict.gap_to_outperform_bp>0:
            status="measured_improvement_needed"
            message=(f"Current project has a confirmed conservative {script.facet} "
                     "shortfall under a matched adversarial replay.")
            reason=None
        else:
            status="measured_candidate_strength"
            message="This build meets this specific measured comparison; continue adversarial regression."
            reason=None
        recipe=REMEDIATIONS[script.axis]
        action=(f"Preserve {', '.join(original.identity_pillars)}. "
                f"{recipe[0]} {recipe[1]}")
        base=(10000 if status=="unmeasured" else
              max(0,verdict.gap_to_outperform_bp or 0))
        priority=min(100000,base*6+
                     (15000 if script.axis in {"gameplay","storyline"} else 8000))
        results.append(ProjectCriticism(
            script.facet,script.axis,status,
            verdict.original_conservative_lower_bp if has_data else None,
            verdict.rival_conservative_upper_bp if has_data else None,
            message,action,
            "Re-execute script "+script.protocol_digest+" with scenario "+
            script.scenario_digest+" and a separate signed negative control.",
            original.identity_pillars,script.digest,priority,reason))
    return CurrentProjectCritique(
        snapshot.digest,original.title_id,dossier.enemy_id,len(results),
        tuple(sorted(results,key=lambda x:(-x.priority,x.domain,x.facet))),
        sum(r.status=="unmeasured" for r in results),
        trusted and snapshot.state=="instrumented_build" and
        bool(original_measurements))


__all__=["UserGameSnapshot","ReviewedUserProjectEvidence",
         "sign_project_evidence","ProjectCriticism",
         "CurrentProjectCritique","critique_current_user_game"]
