"""Rights-gated peer wisdom for Dragon, Wiki, Jeeves and HOAG.

The input is the existing reviewed source library plus a *canonical* cleared
rights packet, not crawled page text. Distillation keeps concepts, uncertainty,
source lineage and conditional research tasks. No third-party quotes, videos,
articles, model weights, or copyrighted expression are copied to an almanac.

Jeeves reasoning / Wiki confidence / HOAG quality are explicit advisory lanes,
not impersonated runtime attestations or a substitute for benchmark results.
"""
from __future__ import annotations

from collections import Counter,defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import os

from .contracts import canonical_json,canonical_digest
from .reviewed_knowledge import (
    ReviewedKnowledgeStore,KnowledgeBrief,KnowledgeError,
)
from .knowledge_rights_bridge import (
    ClearedResearchPacket,require_cleared_research_current,
)
from .rights import RightsLedger,UseKind,RightsState
from .game_project_workspace import GameWorkspace

KINDS=frozenset({"video","article","blog","paper","technical_report",
                 "community_review","original_playtest"})
_ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA=re.compile(r"^[a-f0-9]{64}$")


class WisdomFusionError(ValueError):
    """Adversarial peer evidence is stale, unsupported, or legally unqualified."""


@dataclass(frozen=True,slots=True)
class SourceMediaReceipt:
    source_id: str
    revision_digest: str
    media_kind: str
    peer_review_receipt_digest: str | None = None

    def __post_init__(self):
        if (not isinstance(self.source_id,str) or not _ID.fullmatch(self.source_id)
                or not isinstance(self.revision_digest,str)
                or not _SHA.fullmatch(self.revision_digest)
                or self.media_kind not in KINDS
                or (self.peer_review_receipt_digest is not None and (
                    not isinstance(self.peer_review_receipt_digest,str)
                    or not _SHA.fullmatch(self.peer_review_receipt_digest)))):
            raise WisdomFusionError("typed peer medium and revision evidence required")

    def payload(self):
        return dict(source_id=self.source_id,
                    revision_digest=self.revision_digest,
                    media_kind=self.media_kind,
                    peer_review_receipt_digest=self.peer_review_receipt_digest,
                    peer_review_evidence_claimed_not_cryptographically_verified=self.peer_review_receipt_digest is not None)


@dataclass(frozen=True,slots=True)
class DragonWisdomAlmanac:
    owner: str
    project_id: str
    knowledge_root: str
    rights_digest: str
    brief_digest: str
    clearance_digest: str
    sources: tuple[dict,...]
    lenses: tuple[dict,...]
    condition_plans: tuple[dict,...]
    conflicts: tuple[str,...]
    independent_source_groups: int

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.dragon_peer_wisdom.v1",
            owner=self.owner,project_id=self.project_id,
            knowledge_root=self.knowledge_root,
            rights_digest=self.rights_digest,
            brief_digest=self.brief_digest,
            clearance_digest=self.clearance_digest,
            sources=list(self.sources),lenses=list(self.lenses),
            condition_plans=list(self.condition_plans),
            conflicts=list(self.conflicts),
            independent_source_groups=self.independent_source_groups,
            source_kinds=sorted({x["media_kind"] for x in self.sources}),
            wiki_evidence_verified_via_live_store=True,
            jeeves_research_logic_advisory_only=True,
            hoag_competitor_scores_not_fabricated=True,
            legality_weight_is_reference_use_gate_not_legal_opinion=True,
            source_copyrighted_text_or_video_copied=False,
            asserted_peer_review_identity_not_treated_as_signature=True,
            training_examples_exported=False,
            trained_llm_weights_modified=False,
            training_use_authorized=False,
            requires_new_canonical_original_gameplay_for_training=True,
            can_promote_model=False,
        )


def distill_dragon_peer_wisdom(
    library: ReviewedKnowledgeStore,
    brief: KnowledgeBrief,
    packet: ClearedResearchPacket,
    rights: RightsLedger,
    media_receipts: tuple[SourceMediaReceipt,...],*,
    authorized: bool,
)->DragonWisdomAlmanac:
    if not authorized:
        raise PermissionError("Wiki-Dragon knowledge distillation needs operator authority")
    if (not isinstance(library,ReviewedKnowledgeStore)
            or not isinstance(brief,KnowledgeBrief)
            or not isinstance(packet,ClearedResearchPacket)
            or not isinstance(rights,RightsLedger)):
        raise WisdomFusionError("existing canonical Wiki knowledge and rights actors required")
    if (type(media_receipts) is not tuple or not 1<=len(media_receipts)<=40
            or any(not isinstance(x,SourceMediaReceipt) for x in media_receipts)):
        raise WisdomFusionError("bounded independent source-medium proof required")
    library.require_fresh_brief(brief,authorized=True)
    require_cleared_research_current(packet,library,rights,authorized=True)
    if (brief.scope!="design_reference" or brief.owner!=packet.owner
            or brief.knowledge_root!=packet.knowledge_root
            or brief.to_payload()["brief_digest"]!=packet.research_brief_digest
            or canonical_digest([hit.to_payload() for hit in brief.citations])
               !=canonical_digest([hit.to_payload() for hit in packet.citations])
            or not brief.citations):
        raise WisdomFusionError("review evidence and rights clearance must bind one exact brief")
    medium={x.source_id:x for x in media_receipts}
    if (len(medium)!=len(media_receipts)
            or set(medium)!={hit.source_id for hit in brief.citations}):
        raise WisdomFusionError("every cited source must have exactly one medium receipt")
    source_versions={}
    for hit in brief.citations:
        kind=medium[hit.source_id]
        if kind.revision_digest!=hit.revision_digest:
            raise WisdomFusionError("media classification does not bind the exact reviewed revision")
        record=rights.source(hit.source_id)
        if (UseKind.FACTS_IDEAS_REFERENCE not in record.allowed_uses
                or record.rights_state in {RightsState.UNKNOWN_QUARANTINE,RightsState.FORBIDDEN}):
            raise WisdomFusionError("source reference rights revoked or absent")
        source_versions[hit.source_id]=dict(
            source_id=hit.source_id,revision_digest=hit.revision_digest,
            rights_binding_digest=record.rights_binding_digest,
            source_text_digest=hit.source_text_digest,
            source_url=hit.source_url,
            license_id=hit.license_id,
            media_kind=kind.media_kind,
            peer_review_evidence_unverified=kind.peer_review_receipt_digest,
            dependence_groups=sorted({
                x.dependence_group for x in brief.citations
                if x.source_id==hit.source_id
            }),
            facts_ideas_reference_only=True,
            automated_model_training_not_granted=True,
        )
    # One dependence group gets ONE weighted vote per mechanic and stance.
    # Repeating a popular article/video/blog cannot inflate Wiki confidence.
    votes={}
    for hit in brief.citations:
        key=(hit.mechanic,hit.dependence_group,hit.stance)
        # A hash supplied by the caller does not prove that independent peer
        # review happened. It must not increase epistemic weight.
        effective=min(hit.confidence_ppm,650000)
        votes[key]=max(votes.get(key,0),effective)
    grouped=defaultdict(lambda:{"supports":[],"challenges":[],"uncertain":[]})
    for (mechanic,group,stance),confidence in sorted(votes.items()):
        grouped[mechanic][stance].append((group,confidence))
    lenses=[]
    plans=[]
    for mechanic,stance_map in sorted(grouped.items()):
        supporters=stance_map["supports"]
        challengers=stance_map["challenges"]
        uncertain=stance_map["uncertain"]
        support_groups={group for group,_ in supporters}
        challenge_groups={group for group,_ in challengers}
        independent= len({g for group in stance_map.values()
                          for g,_ in group})
        contradictory=bool(supporters and challengers)
        # Confidence is a capped *research heuristic*; it is never a model
        # posterior, calibrated probability, license opinion or proof of truth.
        average_support=(sum(conf for _,conf in supporters)//len(supporters)
                         if supporters else 0)
        confidence=min(average_support,650000 if independent<2 else 900000)
        ready=(len(support_groups)>=2 and not contradictory
               and not uncertain and confidence>=650000)
        if contradictory:
            mode="resolve_peer_conflict"
            action="Acquire an independent primary source or original canonical playtest resolving both hypotheses."
        elif not supporters or uncertain:
            mode="increase_evidence"
            action="Acquire independently reviewed original evidence and test the missing mechanism."
        elif not ready:
            mode="test_unconfirmed_hypothesis"
            action="Create original game TRAIN-world checks and separate frozen validation/test worlds."
        else:
            mode="propose_original_experiment"
            action="Design distinct original TRAIN game cases; validate and test them independently before any weight fitting."
        lenses.append(dict(
            mechanic=mechanic,source_group_count=independent,
            support_groups=len(support_groups),
            challenge_groups=len(challenge_groups),
            uncertain_groups=len({group for group,_ in uncertain}),
            conflict=contradictory,
            wiki_reference_confidence_ppm=confidence,
            hoag_competitive_readiness="research_only" if ready else "not_ready",
            jeeves_conditional_reasoning=mode,
            no_measured_model_quality_implied=True,
        ))
        plans.append(dict(
            mechanic=mechanic,if_condition=mode,
            then_action=action,
            requires_wiki_recheck=True,
            requires_legal_recheck=True,
            requires_new_train_only_gameplay=True,
            execute_without_operator=False,
        ))
    return DragonWisdomAlmanac(
        brief.owner,packet.project_id,brief.knowledge_root,
        packet.rights_ledger_digest,brief.to_payload()["brief_digest"],
        packet.to_payload()["packet_digest"],
        tuple(source_versions[k] for k in sorted(source_versions)),
        tuple(lenses),tuple(plans),brief.conflicts,
        len({hit.dependence_group for hit in brief.citations}),
    )


def publish_dragon_almanac(root: str|Path,almanac: DragonWisdomAlmanac,*,
                          authorized: bool)->str:
    """Crash-safe content-addressed, no-overwrite Dragon almanac archive."""
    if not authorized:
        raise PermissionError("Dragon peer archive requires operator permission")
    if not isinstance(almanac,DragonWisdomAlmanac):
        raise WisdomFusionError("only previously reviewed typed almanacs may be recorded")
    workspace=GameWorkspace(root)
    folder=workspace.root/"training"/"dragon_peer_almanacs"
    if folder.is_symlink():
        raise WisdomFusionError("untrusted almanac destination")
    folder.mkdir(exist_ok=True)
    if not folder.is_dir():
        raise WisdomFusionError("almanac archive is not a folder")
    filename=folder/(almanac.digest+".json")
    if filename.is_symlink():
        raise WisdomFusionError("untrusted archived almanac symlink")
    payload=(canonical_json(almanac.payload())+"\n").encode("utf-8")
    if len(payload)>512_000:
        raise WisdomFusionError("almanac exceeds bounded source-safe knowledge budget")
    if filename.exists():
        if filename.read_bytes()!=payload:
            raise WisdomFusionError("content-addressed almanac overwrite attempt")
        return almanac.digest
    try:
        with filename.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if filename.is_symlink() or filename.read_bytes()!=payload:
            raise WisdomFusionError("concurrent almanac changed after approval")
    return almanac.digest


__all__=["KINDS","WisdomFusionError","SourceMediaReceipt",
         "DragonWisdomAlmanac","distill_dragon_peer_wisdom",
         "publish_dragon_almanac"]
