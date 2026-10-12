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
