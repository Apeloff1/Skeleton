"""Cross-cycle rival convergence trajectories and adversarial response budgets.

Only audited reports for the SAME immutable original plan can be compared.
Trend is a bounded, deterministic and explicitly strategic work signal:
it cannot promote a reviewer model, mutate a game or infer a competitor's
quality from marketing activity.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter

from .contracts import canonical_digest
from .rival_convergence_observatory import (
    PlannedTitle, ConvergenceReport, CompetitiveError,
)


@dataclass(frozen=True,slots=True)
class CompetitiveTrajectory:
    original_plan_digest: str
    competitor_id: str
    history_digests: tuple[str,...]
    trend: str
    overlap_change: float
    novelty_features: tuple[str,...]
    withdrawn_features: tuple[str,...]
    newly_confirmed_enemy: bool
    consecutive_enemy_cycles: int
    recommended_adversarial_effort: int
    priority_actions: tuple[dict,...]

    def payload(self):
        body=dict(
            schema="skeleton.game_builder.competitive_trajectory.v1",
            original_plan_digest=self.original_plan_digest,
            competitor_id=self.competitor_id,
            history_digests=list(self.history_digests),
            trend=self.trend,overlap_change=self.overlap_change,
            novelty_features=list(self.novelty_features),
            withdrawn_features=list(self.withdrawn_features),
            newly_confirmed_enemy=self.newly_confirmed_enemy,
            consecutive_enemy_cycles=self.consecutive_enemy_cycles,
            recommended_adversarial_effort=self.recommended_adversarial_effort,
            priority_actions=list(self.priority_actions),
            competitor_title_only_not_a_person=True,
            trend_evidence_only_not_a_fact_about_copyright=True,
            actual_quality_advancement_not_yet_proven=True,
            auto_deployment=False,
        )
        return {**body,"trajectory_digest":canonical_digest(body)}

    @property
    def digest(self):
        return self.payload()["trajectory_digest"]


def trace_competitive_trajectory(
    plan:PlannedTitle,reports:tuple[ConvergenceReport,...],*,authorized:bool
)->CompetitiveTrajectory:
    if not authorized:
        raise PermissionError("historical rival assessment requires trusted operator")
    if not isinstance(plan,PlannedTitle) or type(reports) is not tuple or not 2<=len(reports)<=64:
        raise CompetitiveError("at least two and at most 64 audited rival reports required")
    if any(not isinstance(report,ConvergenceReport) for report in reports):
        raise CompetitiveError("typed historical rival observations required")
    if len({r.digest for r in reports})!=len(reports):
        raise CompetitiveError("cycle replay cannot manufacture continuous competitive pressure")
    for i,report in enumerate(reports):
        if (not isinstance(report,ConvergenceReport)
                or report.original_plan_digest!=plan.digest
                or report.project_id!=plan.project_id
                or report.competitor_id!=reports[0].competitor_id):
            raise CompetitiveError("history cannot pool unrelated original titles")
        if (i==0 and report.previous_report_digest is not None
                or i>0 and report.previous_report_digest!=reports[i-1].digest):
            raise CompetitiveError("historical report hash chain has a missing/stale cycle")
        if any(o.protected_identity_digest!=plan.distinctive_signature_digest
               for o in report.orders):
            raise CompetitiveError("history mutated the original game identity")
    last=reports[-1]
    prior=reports[-2]
    new=tuple(sorted(set(last.convergent_features)-set(prior.convergent_features)))
    lost=tuple(sorted(set(prior.convergent_features)-set(last.convergent_features)))
    change=round(last.overlap-prior.overlap,6)
    enemy_streak=0
    for report in reversed(reports):
        if report.status!="enemy":
            break
        enemy_streak+=1
    became_enemy=(last.status=="enemy" and prior.status!="enemy")
    if became_enemy:
        trend="new_enemy"
    elif change>=0.10:
        trend="rapid_convergence"
    elif change>=0.02:
        trend="rising_convergence"
    elif change<=-0.10:
        trend="cooling_convergence"
    elif change<=-0.02:
        trend="declining_convergence"
    else:
        trend="stable_convergence"
    # Higher exertion prioritizes original-game work, not additional scrapes:
    # novelty/acceleration trigger deeper on-device original-game mirror passes.
    effort=min(100,25+(25 if last.status=="enemy" else 0)
               +(20 if became_enemy else 0)
               +(20 if change>=0.10 else 0)
               +(5*min(4,len(new))))
    actions=[]
    if last.status!="enemy":
        actions.append(dict(
            stage="wiki_independent_source_review",
            priority=85,objective=(
                "Qualify fresh independent public evidence; no competitive claim"
                " from source count, press headlines or unmeasured rating.")))
    else:
        actions.append(dict(
            stage="builder_original_implementation",
            priority=100,objective=(
                "Advance all concrete quality work orders with original gameplay"
                " and preserve the precommitted original design signature.")))
        actions.append(dict(
            stage="mirror_adversarial_gameplay",
            priority=effort,objective=(
                "Replay new original game failures, unconventional NPC/quest paths,"
                " platform limits, accessibility and originality counterexamples.")))
        actions.append(dict(
            stage="hoag_independent_competitive_benchmark",
            priority=95,objective=(
                "Prove improvement on preregistered comparable player-facing"
                " benchmarks; withhold outperformance claims if evidence is absent.")))
    if new:
        actions.append(dict(
            stage="dragon_wiki_original_research",
            priority=90,objective=(
                "Review emerging rival-feature hypotheses through lawful"
                " reference citations; generate original alternate solutions,"
                " never copy assets or source expressions.")))
    return CompetitiveTrajectory(
        plan.digest,last.competitor_id,tuple(r.digest for r in reports),
        trend,change,new,lost,became_enemy,enemy_streak,
        effort,tuple(actions),
    )


__all__=["CompetitiveTrajectory","trace_competitive_trajectory"]
