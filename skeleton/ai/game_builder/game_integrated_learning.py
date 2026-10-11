"""Jeeves/Wiki/HOAG/Dragon research-to-training bridge, with no rights bypass.

Jeeves: deterministic conditional experiment plans, not counterfeit LLM output.
Wiki: exact current, independently reviewed knowledge briefs.
Dragon: original domain almanac of cited, rights-cleared knowledge lenses.
HOAG: a typed predeclared model quality standard, not a fabricated leaderboard.
Mirror: genuinely trained ranker challenges on *original TRAIN games* only.

A research note never becomes a gradient. At least two unrelated, source-
reviewed original TRAIN projects must actually exercise the targeted mechanic.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .contracts import canonical_digest
from .game_training_flow import FlowPlan
from .game_model_promotion import PromotionStandard,PromotionError
from .game_reviewer_optimizer import (
    OptimizerSchedule,OptimizationResult,optimize_review_weights,
)
from .game_dragon_peer_wisdom import (
    SourceMediaReceipt,DragonWisdomAlmanac,distill_dragon_peer_wisdom,
)
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import ClearedResearchPacket
from .rights import RightsLedger


@dataclass(frozen=True,slots=True)
class IntegratedLearningCycle:
    source_evidence_digest: str
    original_game_plan_digest: str
    quality_standard_digest: str
    eligible_mechanics: tuple[str,...]
    gaps: tuple[dict,...]
    dragon: DragonWisdomAlmanac
    optimization: OptimizationResult | None

    def payload(self):
        return dict(
            schema="skeleton.game_builder.integrated_reviewer_learning_cycle.v1",
            research_digest=self.source_evidence_digest,
            original_game_plan_digest=self.original_game_plan_digest,
            quality_standard_digest=self.quality_standard_digest,
            eligible_mechanics=list(self.eligible_mechanics),
            gaps=list(self.gaps),
            dragon_almanac_digest=self.dragon.digest,
            optimizer=(self.optimization.payload()
                       if self.optimization else None),
            status=("evaluated" if self.optimization
                    else "await_independently_replayed_train_games"),
            jeeves_knowledge_is_advisory_not_training_text=True,
            wiki_claims_have_reviewed_provenance=True,
            hoag_predeclared_competitive_standard=True,
            source_video_article_blog_data_directly_in_gradients=False,
            source_rights_rechecked_before_training=True,
            all_weight_changes_confined_to_local_reviewer=True,
            automatic_model_deployment=False,
        )


def run_integrated_learning_cycle(
    library: ReviewedKnowledgeStore,brief: KnowledgeBrief,
    packet: ClearedResearchPacket,rights: RightsLedger,
    media: tuple[SourceMediaReceipt,...],
    original_games: FlowPlan,*,
    authorized: bool,
    standard: PromotionStandard=PromotionStandard(),
    schedule: OptimizerSchedule=OptimizerSchedule(),
    champion: dict|None=None,
)->IntegratedLearningCycle:
    if not authorized:
        raise PermissionError("multi-agent game AI improvement requires operator authority")
    if (not isinstance(original_games,FlowPlan)
            or not isinstance(standard,PromotionStandard)
            or not isinstance(schedule,OptimizerSchedule)):
        raise PromotionError("typed original-game TRAIN plan and competitive standard required")
    dragon=distill_dragon_peer_wisdom(
        library,brief,packet,rights,media,authorized=True)
    targets={p["mechanic"] for p in dragon.lenses}
    if not targets or len(targets)>32:
        raise PromotionError("bounded reviewed-game knowledge targets required")
    source_groups=defaultdict(set)
    for entry in original_games.selected:
        if entry.split!="train":
            continue
        # Only independently replayed original-game receipts in TRAIN may
        # supply training evidence; a source article's mechanic tags never do.
        mechanic=entry.evidence.get("mechanic")
        if mechanic in targets and entry.approval=="quarantined":
            source_groups[mechanic].add(entry.project_digest)
    eligible=[]
    gaps=[]
    for lens in dragon.lenses:
        mechanic=lens["mechanic"]
        if lens["conflict"]:
            reason="unresolved_independent_peer_conflict"
        elif lens["support_groups"]<2:
            reason="insufficient_independent_wiki_sources"
        elif lens["hoag_competitive_readiness"]!="research_only":
            reason="wiki_wisdom_below_quality_frontier"
        elif len(source_groups[mechanic])<2:
            reason="missing_two_independent_original_train_worlds"
        else:
            eligible.append(mechanic)
            continue
        gaps.append(dict(mechanic=mechanic,reason=reason,
                         train_from_unlicensed_source=False,
                         acquire_new_original_replay=True))
    # Never proceed with partial coverage while reporting an integrated
    # full-mechanic improvement, even if one easy lane is already testable.
    optimization=None
    if not gaps:
        optimization=optimize_review_weights(
            original_games,authorized=True,standard=standard,
            schedule=schedule,champion=champion)
    return IntegratedLearningCycle(
        dragon.digest,canonical_digest(original_games.payload()),
        standard.digest,tuple(sorted(eligible)),
        tuple(gaps),dragon,optimization,
    )


__all__=["IntegratedLearningCycle","run_integrated_learning_cycle"]
