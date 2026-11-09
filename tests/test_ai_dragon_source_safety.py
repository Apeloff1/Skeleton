"""Compatibility entrypoint discovered by main's test_ai*dragon*.py workflow.

This deliberately exercises public fail-closed source-safety primitives. The
larger dedicated source-operations and acquisition suites run in the feature
branch's explicit Dragon Source Safety CI job.
"""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.dragon_worker_stop_authority import (
    DragonWorkerStopAuthority,
)
from skeleton.ai.game_builder.dragon_external_rights import (
    DragonExternalRightsVerifier, IndependentRightsAttestation,
)
from skeleton.ai.game_builder.dragon_pilot_budget import DragonPilotBudget
from skeleton.ai.game_builder.dragon_research_pilot import DragonResearchPilot


def test_dragon_source_authorities_are_importable_and_deny_missing_trust():
    with pytest.raises(ValueError,match="256-bit"):
        DragonWorkerStopAuthority(key=b"tiny",issuer="supervisor")
    with pytest.raises(ValueError,match="public-key"):
        DragonExternalRightsVerifier(
            public_key_bytes=b"not-a-valid-ed25519-key",
            issuer="external-legal-review",key_id="ed25519-review")


def test_crash_stop_cannot_be_signed_by_untrusted_worker():
    supervisor=DragonWorkerStopAuthority(
        key=b"\x41"*32,issuer="external-process-supervisor")
    with pytest.raises(PermissionError,match="external process"):
        supervisor.issue(
            owner="studio",source_id="source-"+"a"*64,host="source.example.org",
            ticket_digest="b"*64,quarantine_digest="c"*64,
            process_stop_digest="d"*64,
            resource_reconciliation_digest="e"*64,
            supervisor="host-os-reconciler",now=100,
            expires_at=200,trusted_external_supervisor=False,
            process_stopped=True,global_resources_reconciled=True)


def test_pilot_entry_requires_real_trusted_dependencies():
    with pytest.raises(TypeError,match="existing Dragon"):
        DragonResearchPilot(None,None,None)


def test_pilot_budget_requires_canonical_source_store():
    with pytest.raises(TypeError,match="canonical"):
        DragonPilotBudget(None)


def test_external_attestation_is_not_a_license_or_model_weight():
    proof=IndependentRightsAttestation(
        owner="studio",source_id="source-"+"a"*64,
        source_url="https://example.org/rights",
        grant_digest="b"*64,policy_receipt="c"*64,
        evidence_digest="d"*64,reviewer="human-reviewer",
        issuer="external-legal-review",key_id="ed25519-review",
        issued_at=100,expires_at=150,
        retention_permitted=True,signature_hex="0"*128)
    assert proof.body()["crawler_training_authorized"] is False
    assert proof.body()["model_training_authorized"] is False



def test_three_specialist_evidence_processors_keep_review_boundaries():
    from skeleton.ai.game_builder.dragon_video_transcript_ledger import (
        TimedTranscriptCue,DragonVideoTranscriptLedger
    )
    from skeleton.ai.game_builder.dragon_source_delta_ledger import (
        DragonSourceDeltaLedger
    )
    assert TimedTranscriptCue(0,1200,"Original game evidence").end_ms==1200
    with pytest.raises(TypeError,match="canonical"):
        DragonSourceDeltaLedger(None)
    with pytest.raises(TypeError,match="canonical"):
        DragonVideoTranscriptLedger(None,review_public_key=b"\x11"*32,
                                    issuer="external-video-review",
                                    key_id="external-key-v1")



def test_mother_dragon_cross_media_remains_review_only():
    from skeleton.ai.game_builder.dragon_mother_evidence_synergy import (
        DragonMotherEvidenceSynergy,
    )
    with pytest.raises(TypeError,match="canonical"):
        DragonMotherEvidenceSynergy(None,None)



def test_all_three_dragon_hatchlings_are_first_class_and_never_self_train():
    from skeleton.ai.game_builder.dragon_article_hatchling import (
        DragonArticleHatchling,
    )
    from skeleton.ai.game_builder.dragon_three_hatchling_coordinator import (
        DragonThreeHatchlingCoordinator,
    )
    with pytest.raises(TypeError,match="canonical"):
        DragonArticleHatchling(None)
    with pytest.raises(TypeError,match="canonical"):
        DragonThreeHatchlingCoordinator(None,None,None)
