"""Focused regressions for backend contracts repaired on 2026-09-19."""

from __future__ import annotations

import asyncio

from starlette.requests import Request

import api_middleware
from core.curiosity_engine import Inquiry
from core.curiosity_research_pipeline import EnsembleCuriosityResearcher
from core.product_control_plane import ProductControlPlane


def _request(request_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [(b"x-request-id", request_id.encode("latin-1"))],
            "client": ("198.51.100.10", 1234),
            "server": ("testserver", 80),
        }
    )


def test_generated_request_id_keeps_compact_public_contract() -> None:
    generated = api_middleware._request_id(
        _request("contains unsafe whitespace")
    )
    assert len(generated) == 16
    assert generated.isalnum()


def test_safe_caller_request_id_is_preserved_exactly() -> None:
    value = "trace-01.prod:abc_123"
    assert api_middleware._request_id(_request(value)) == value


async def _model(task, prompt, system):
    del task, prompt, system
    return {
        "summary": "hypothesis",
        "claims": ["Exact candidate claim 20 percent."],
        "questions": [],
        "contradictions": [],
        "tags": [],
    }


def _inquiry() -> Inquiry:
    return Inquiry(
        id="inq-regression",
        subject="exact claim",
        questions=("What is supported?",),
        context_record_ids=(),
        keywords=("exact",),
        score=0.8,
        reason="test",
    )


def test_verified_legacy_locator_binds_only_exact_candidate_label() -> None:
    exact = "Exact candidate claim 20 percent."

    async def search(inquiry, questions):
        del inquiry, questions
        return [
            {
                "source": "paper-a",
                "locator": "doi:example",
                "kind": "primary_empirical",
                "independence_group": "lab-a",
                "quality": 0.9,
                "supports_claims": [exact, "Adjacent but different claim."],
                "verified_locator": True,
                "reproducible": True,
                "peer_reviewed": True,
            }
        ]

    result = asyncio.run(
        EnsembleCuriosityResearcher(
            _model,
            source_search=search,
            models=("a", "b"),
        )(_inquiry(), {})
    )
    assert len(result["claim_evidence"][exact]) == 1
    assert "Adjacent but different claim." not in result["claim_evidence"]
    binding = result["claim_evidence"][exact][0]["citation_binding"]
    assert binding["binding_method"] == "verified_locator_exact_claim"


def test_unverified_legacy_locator_cannot_use_compatibility_binding() -> None:
    exact = "Exact candidate claim 20 percent."

    async def search(inquiry, questions):
        del inquiry, questions
        return [
            {
                "source": "paper-a",
                "locator": "doi:example",
                "supports_claims": [exact],
                "verified_locator": False,
            }
        ]

    result = asyncio.run(
        EnsembleCuriosityResearcher(
            _model,
            source_search=search,
            models=("a",),
        )(_inquiry(), {})
    )
    assert result["claim_evidence"][exact] == []


def test_verified_locator_never_semantically_binds_nonexact_label() -> None:
    exact = "Exact candidate claim 20 percent."

    async def search(inquiry, questions):
        del inquiry, questions
        return [
            {
                "source": "paper-a",
                "locator": "doi:example",
                "supports_claims": ["Exact candidate claim 21 percent."],
                "verified_locator": True,
            }
        ]

    result = asyncio.run(
        EnsembleCuriosityResearcher(
            _model,
            source_search=search,
            models=("a",),
        )(_inquiry(), {})
    )
    assert result["claim_evidence"][exact] == []


def test_lifecycle_pending_keeps_operation_or_none_contract(tmp_path) -> None:
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(
        capability_id="studio",
        domain="studio",
        action="project.create",
        principal="creator",
        actor_weight=0,
        payload={"title": "Lifecycle"},
    )
    before = plane.operation_lifecycle(operation.id)
    assert isinstance(before["pending"], dict)
    assert before["pending"]["operation_id"] == operation.id
    assert before["pending_present"] is True

    assert asyncio.run(
        plane.execute_registered(operation.outbox_seq)
    ) is True
    after = plane.operation_lifecycle(operation.id)
    assert after["pending"] is None
    assert after["pending_operation"] is None
    assert after["pending_present"] is False
    assert after["receipt"] is not None


def test_confirmed_lifecycle_retains_receipt_after_pending_is_removed(tmp_path) -> None:
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(
        capability_id="studio",
        domain="studio",
        action="project.create",
        principal="creator",
        actor_weight=0,
        payload={"title": "Receipt"},
    )
    assert asyncio.run(
        plane.execute_registered(operation.outbox_seq)
    )
    lifecycle = plane.operation_lifecycle(operation.id)
    assert lifecycle["state"] == "confirmed"
    assert lifecycle["pending"] is None
    assert lifecycle["receipt"]["operation_id"] == operation.id
