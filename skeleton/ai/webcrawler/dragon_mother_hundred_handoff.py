"""Strict 100-matrix admission wrapper for the existing mother-to-shadow lane.

The legacy handoff preserves its older approved workflows. Opting into this
entry point adds signed 100-matrix fact review before invoking the original
idle worker and sparse shadow coordinator. Not a neural-weight promotion.
"""
from __future__ import annotations

from .dragon_hundred_matrix_scrutiny import SignedMatrixFinding,scrutinize_one_hundred
from .dragon_mother_shadow_handoff import MotherGleanHandoff,run_mother_to_shadow
from .dragon_mother_glean_ledger import MotherGleanLedger
from .dragon_shadow_weight_automation import ShadowWeightAutomation
from .dragon_shadow_weight_coordinator import ReviewedAcquisition
from .dragon_mother_glean_matrix import HatchlingReceipt
from .dragon_nest_progression import DragonNest
from .dragon_nest_research_scheduler import IdleResearchPlan
from .dragon_resource_session import HardwareSample
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore

def run_hundred_matrix_mother_to_shadow(
    ledger:MotherGleanLedger,automation:ShadowWeightAutomation,
    library:ReviewedKnowledgeStore,nest:DragonNest,
    plan:IdleResearchPlan,
    reviewed:tuple[ReviewedAcquisition,...],
    acquisitions:tuple[HatchlingReceipt,...], *,
    now:str,idle_since:str,
    hardware:HardwareSample,hardware_now:float,
    consented:bool,background_allowed:bool,
    owner_authorized:bool,privacy_clear:bool,
    knowledge_digest:str,findings:tuple[SignedMatrixFinding,...],
    reviewer_public_key:bytes,reviewer:str,key_id:str,review_at:int,
)->MotherGleanHandoff:
    if (owner_authorized is not True or consented is not True
        or background_allowed is not True or privacy_clear is not True):
        raise PermissionError("100-matrix handoff requires lawful idle admission")
    if not isinstance(plan,IdleResearchPlan):
        raise TypeError("canonical idle research plan required")
    report=scrutinize_one_hundred(
        plan.owner,knowledge_digest,findings,public_key=reviewer_public_key,
        trusted_reviewer=reviewer,key_id=key_id,now=review_at)
    if report["shadow_review_proposal_eligible"] is not True:
        raise PermissionError("all 100 independently signed matrices must pass")
    # The original coordinator STILL verifies exact nest/plan/acquisition
    # owner identity, hardware, consent, review and human promotion gates.
    return run_mother_to_shadow(
        ledger,automation,library,nest,plan,reviewed,acquisitions,
        now=now,idle_since=idle_since,hardware=hardware,
        hardware_now=hardware_now,consented=consented,
        background_allowed=background_allowed,owner_authorized=True,
        privacy_clear=privacy_clear)
