"""Dragon native post-weight research agenda: repeat, explain, disconfirm.

It is dangerous to feed heldout samples or performance predictions into
training. Only high-level failures, aggregate family hashes and unmeasured
knowledge facets become new public-research interests. Dragon's existing
research planner returns discovery QUERIES, not collected papers/videos;
actual source admission still requires Wiki/rights/reviewer approval.
"""
from __future__ import annotations
from dataclasses import dataclass

from .contracts import canonical_digest
from .game_post_weight_forensics import PostWeightReport
from .game_dragon_peer_wisdom import DragonWisdomAlmanac
from .game_model_promotion import PromotionError
from ..webcrawler.dragon_research_missions import (
    ResearchInterest,MissionPolicy,ResearchMission,plan_research,
)

MOTIFS={
    "regression":("game AI evidence project nonregression independent gameplay",0.99),
    "adversarial_escape":("game AI red team counterfactual dangerous miss prevention",0.99),
    "danger_recall":("game AI reviewer high severity recall source validity",0.98),
    "metamorphic_robustness":("machine learning metamorphic tests data shortcut detection",0.96),
    "recall_confidence":("game AI independent game cohorts Wilson recall interval",0.94),
    "class_coverage":("balanced independent video game failure controls",0.88),
    "project_diversity":("game AI generalization across originally authored worlds",0.90),
    "family_coverage":("game testing adversarial attack family coverage",0.92),
    "project_quality":("game AI per world evaluation and replay failure",0.87),
    "balanced_quality":("game AI balanced class validation metrics",0.86),
    "generalization":("game AI out of distribution original world transfer",0.94),
    "calibration":("binary model scoring Brier calibration evaluation",0.84),
    "frontier_expansion":("game AI rigorous competitive quality new evaluation standards",0.78),
    "unclassified_gap":("game design evaluation failure independent test methodology",0.90),
}
DOMAIN_TOPICS=(
    "gameplay npc witnessed event quest causality original world replay",
    "game graphics frame pacing accessibility original art identity",
    "game sound interactive audio caption spatial hearing validation",
    "game story branching causal nonterminal world player agency",
)


@dataclass(frozen=True,slots=True)
class PostWeightDragonMission:
    source_report_digest: str
    previous_wisdom_digest: str
    mode: str
    topics: tuple[str,...]
    native_mission: ResearchMission
    coverage_family_count: int
    actual_fetches: int=0
    actual_cleared_training_sources: int=0

    def payload(self):
        return dict(
            schema="skeleton.game_builder.post_weight_dragon_mission.v1",
            post_weight_digest=self.source_report_digest,
            first_wisdom_digest=self.previous_wisdom_digest,
            mode=self.mode,
            topics=list(self.topics),
            native_fingerprint=self.native_mission.fingerprint,
            query_count=len(self.native_mission.queries),
            coverage_family_count=self.coverage_family_count,
            actual_fetches=self.actual_fetches,
            actual_cleared_training_sources=self.actual_cleared_training_sources,
            metadata_not_relabelled_as_verified_research=True,
            protected_holdout_content_never_queried=True,
            no_automatic_model_gradient_update=True,
        )


def plan_post_weight_dragon_research(
    report: PostWeightReport,
    almanac: DragonWisdomAlmanac,*,
    authorized: bool,consent: bool,
    mode: str="second_glance",
    max_topics: int=18,
)->PostWeightDragonMission:
    if not authorized or not consent:
        raise PermissionError("post-weight Dragon research needs explicit consent")
    if (not isinstance(report,PostWeightReport)
            or not isinstance(almanac,DragonWisdomAlmanac)
            or mode not in {"second_glance","adversarial_reread"}
            or type(max_topics) is not int or not 8<=max_topics<=20):
        raise PromotionError("bound research-only original weight analysis required")
    inputs=[]
    for domain in DOMAIN_TOPICS:
        inputs.append(ResearchInterest(domain,0.98))
    categories=set()
    for entry in report.feedback.objectives:
        category=entry["category"]
        categories.add(category)
        topic,weight=MOTIFS.get(category,MOTIFS["unclassified_gap"])
        inputs.append(ResearchInterest(topic,weight))
    # No raw heldout family/event names; hashed family IDs remain in the
    # forensic report but NEVER become query terms.
    if report.safety_objections:
        inputs.append(ResearchInterest(
            "post training model weight drift negative controls validation",0.99))
        inputs.append(ResearchInterest(
            "independent game AI reviewer post deployment rollback audit",0.98))
    for lens in almanac.lenses:
        if len(inputs)>=max_topics:
            break
        mechanic=lens["mechanic"]
        if (type(mechanic) is not str or len(mechanic)>96 or
                not mechanic.replace("_","").replace("-","").isalnum()):
            raise PromotionError("untrusted Wiki mechanic must not become arbitrary crawler query")
        inputs.append(ResearchInterest(
            "video game "+mechanic.replace("_"," ").replace("-"," ")+" original mechanic evidence",0.75))
    # Repeated categories/source syndication cannot inflate independent
    # research breadth or turn journaled data into new evidence.
    unique={}
    for interest in inputs:
        unique.setdefault(interest.topic,interest)
    if len(unique)>max_topics:
        # Protect each of the four game domains from being squeezed out by
        # correlated high-priority error categories.
        reserved=tuple(unique[domain] for domain in DOMAIN_TOPICS)
        remainder=sorted(
            (item for topic,item in unique.items() if topic not in DOMAIN_TOPICS),
            key=lambda x:(-x.weight,x.topic))
        chosen=reserved+tuple(remainder[:max_topics-len(reserved)])
    else:
        chosen=tuple(unique.values())
    if not set(DOMAIN_TOPICS).issubset({x.topic for x in chosen}):
        raise PromotionError("post-weight research may not omit gameplay, graphics, sound or storyline")
    mission=plan_research(
        almanac.owner,chosen,authorized=True,
        geographic_consent=False,
        policy=MissionPolicy(max_interests=max_topics,
                             max_queries=4*max_topics,
                             include_places=False))
    return PostWeightDragonMission(
        report.digest,almanac.digest,mode,
        tuple(x.topic for x in chosen),mission,len(categories))


__all__=["PostWeightDragonMission","plan_post_weight_dragon_research"]
