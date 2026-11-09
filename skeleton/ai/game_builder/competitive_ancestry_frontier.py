"""Quantified outworking across EVERY reviewed comparable genre generation.

An enemy's current release is not enough: evaluate each ancestor/comparator
under the same script and independent evaluator controls. No missed
generation becomes a fabricated zero. This report can raise, never lower,
the original title's delivery target.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
import hmac

from .contracts import canonical_digest
from .competitive_title_radar import PlannedOriginalTitle,ThreatRadarError,_date
from .competitive_evolution_chain import RivalEvolutionChain
from .competitive_deep_analysis import (
    ScriptedProbe,FacetMeasurement,FacetVerdict,
)
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac


@dataclass(frozen=True,slots=True)
class AncestralFacetFrontier:
    facet: str
    domain: str
    script_digest: str
    strongest_predecessor_id: str|None
    conservative_ancestry_ceiling_bp: int|None
    original_conservative_floor_bp: int|None
    target_floor_bp: int|None
    covered_title_ids: tuple[str,...]
    missing_title_ids: tuple[str,...]
    proved_outclassing: bool
    blockers: tuple[str,...]

    def payload(self):
        return dict(schema="skeleton.game_builder.ancestral_outclassing_frontier.v1",
                    facet=self.facet,domain=self.domain,
                    script_digest=self.script_digest,
                    strongest_predecessor_id=self.strongest_predecessor_id,
                    conservative_ancestry_ceiling_bp=self.conservative_ancestry_ceiling_bp,
                    original_conservative_floor_bp=self.original_conservative_floor_bp,
                    target_floor_bp=self.target_floor_bp,
                    covered_title_ids=list(self.covered_title_ids),
                    missing_title_ids=list(self.missing_title_ids),
                    proved_outclassing=self.proved_outclassing,
                    blockers=list(self.blockers),
                    no_assumed_quality_for_unmeasured_predecessors=True)


@dataclass(frozen=True,slots=True)
class AncestralCompetition:
    original_id: str
    enemy_id: str
    evolution_digest: str
    studies: tuple[AncestralFacetFrontier,...]
    complete_ancestry_outclassed: bool

    def payload(self):
        return dict(
            schema="skeleton.game_builder.genre_ancestry_outclassing.v1",
            original_id=self.original_id,enemy_id=self.enemy_id,
            evolution_digest=self.evolution_digest,
            studies=[x.payload() for x in self.studies],
            complete_ancestry_outclassed=self.complete_ancestry_outclassed,
            implementation_and_release_permission=False)


def evaluate_ancestral_outclassing(
    original: PlannedOriginalTitle,
    chain: RivalEvolutionChain,
    scripts: tuple[ScriptedProbe,...],
    current_verdicts: tuple[FacetVerdict,...],
    ancestor_measurements: tuple[FacetMeasurement,...],
    judges: tuple[TrustedCompetitionJudge,...], *,
    as_of: str,authorized: bool,margin_bp: int=150,
    minimum_judges: int=2,max_age_days: int=180,
)->AncestralCompetition:
    if not authorized:
        raise PermissionError("per-generation competitor verification requires operator authority")
    if (not isinstance(original,PlannedOriginalTitle)
            or not isinstance(chain,RivalEvolutionChain)
            or type(scripts) is not tuple or type(current_verdicts) is not tuple
            or type(ancestor_measurements) is not tuple
            or type(judges) is not tuple
            or len(scripts)!=len(current_verdicts)
            or len({s.digest for s in scripts})!=len(scripts)
            or len(ancestor_measurements)>10000
            or any(not isinstance(x,ScriptedProbe) for x in scripts)
            or any(not isinstance(x,FacetVerdict) for x in current_verdicts)
            or any(not isinstance(x,FacetMeasurement) for x in ancestor_measurements)
            or any(not isinstance(x,TrustedCompetitionJudge) for x in judges)
            or len({x.judge_id for x in judges})!=len(judges)
            or type(margin_bp) is not int or not 50<=margin_bp<=2000
            or type(minimum_judges) is not int or not 2<=minimum_judges<=8
            or type(max_age_days) is not int or not 1<=max_age_days<=365):
        raise ThreatRadarError("typed complete benchmark and ancestor witness evidence required")
    stamp=_date(as_of)
    if not scripts or any(x.subject_id!=chain.enemy_id for x in scripts):
        raise ThreatRadarError("exact opponent script binding required")
    by_script={s.digest:s for s in scripts}
    vals={v.script_digest:v for v in current_verdicts}
    if len(vals)!=len(current_verdicts) or set(vals)!=set(by_script) or any(
            v.facet!=by_script[v.script_digest].facet or
            v.axis!=by_script[v.script_digest].axis
            for v in current_verdicts):
        raise ThreatRadarError("cannot silently omit or reassign deep-analysis facets")
    ancestors=tuple(sorted(set(x.title_id for x in chain.stages)-
                           {chain.enemy_id}))
    allowed=set(ancestors)
    trusted={x.judge_id:x for x in judges}
    if not allowed:
        raise ThreatRadarError("unresolved historical genre ancestry")
    rows=defaultdict(lambda:defaultdict(list))
    dupes=set()
    for row in ancestor_measurements:
        if row.subject_id not in allowed or row.script_digest not in by_script:
            raise ThreatRadarError("cross-genre title or scenario in ancestor benchmark")
        judge=trusted.get(row.evaluator_id)
        if judge is None or not hmac.compare_digest(
                row.signature,_mac(row.body(),judge.key)):
            raise ThreatRadarError("untrusted ancestor score or tampered replay")
        when=_date(row.observed_at)
        if when>stamp or (stamp-when).days>max_age_days:
            raise ThreatRadarError("stale or future ancestor measurement")
        marker=(row.script_digest,row.subject_id,row.evaluator_id)
        if marker in dupes:
            raise ThreatRadarError("duplicate ancestor judge cannot multiply sample size")
        dupes.add(marker)
        rows[row.script_digest][row.subject_id].append(row)
    studies=[]
    for script in scripts:
        verdict=vals[script.digest]
        missing=[]
        coverage=[]
        grades=[]
        for title in ancestors:
            witnesses=rows[script.digest][title]
            if len({w.evaluator_id for w in witnesses})<minimum_judges:
                missing.append(title)
                continue
            coverage.append(title)
            grades.append((max(w.upper_bp for w in witnesses),title))
        blockers=[]
        if missing:
            blockers.append("unmeasured_or_single_source_predecessor")
        if not chain.complete_competitor_coverage:
            blockers.append("incomplete_verified_genre_evolution")
        if (verdict.status=="insufficient_evidence"
                or verdict.original_conservative_lower_bp is None
                or verdict.rival_conservative_upper_bp is None):
            blockers.append("enemy_or_original_quality_not_verified")
        best=max(grades) if grades else None
        # Across ancestry, the worst comparison is the maximum of every
        # reviewed earlier-title upper interval PLUS the modern rival itself.
        ceiling=max(
            (best[0] if best else 0),
            (verdict.rival_conservative_upper_bp or 0),
        ) if best and verdict.rival_conservative_upper_bp is not None else None
        target=min(10000,ceiling+margin_bp) if ceiling is not None else None
        if ceiling is not None and ceiling+margin_bp>10000:
            blockers.append("benchmark_target_exceeds_metric_scale")
        proven=(not blockers and target is not None
                and verdict.original_conservative_lower_bp>=target)
        studies.append(AncestralFacetFrontier(
            script.facet,script.axis,script.digest,
            best[1] if best else None,
            ceiling,verdict.original_conservative_lower_bp,
            target,tuple(coverage),tuple(missing),proven,
            tuple(sorted(set(blockers)))))
    return AncestralCompetition(
        original.title_id,chain.enemy_id,chain.digest,tuple(studies),
        bool(studies) and all(x.proved_outclassing for x in studies))


__all__=["AncestralFacetFrontier","AncestralCompetition",
         "evaluate_ancestral_outclassing"]
