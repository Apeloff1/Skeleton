"""Fail-closed source evidence for authenticated delegated Discourse endpoints."""
from copy import deepcopy
import json
from unittest.mock import patch

from scripts import check_product_surface_specification as surfaces


def _candidate():
    payload = json.loads(surfaces.REGISTRY.read_text(encoding="utf-8"))
    row = next(item for item in payload["surfaces"] if item["surface_id"] == "route:discourse")
    return payload, row


def _errors(payload):
    with patch.object(surfaces, "_load_registry", return_value=deepcopy(payload)):
        return surfaces.validate()


def test_current_delegated_backend_is_source_bound_without_runtime_ready_claim():
    payload, row = _candidate()
    assert payload["runtime_ready_claim"] is False
    assert row["runtime_ready_claim"] is False
    assert row["backend_mode"] == "api"
    assert row["backend_surfaces"] == [
        "/api/discourse/deliberate/async", "/api/discourse/jobs", "/api/discourse/result/",
    ]
    assert _errors(payload) == []


def test_helper_digest_drift_fails_closed():
    payload, row = _candidate()
    row["backend_delegates"][0]["source_sha256"] = "0" * 64
    assert any("delegated backend source_sha256 drift" in item for item in _errors(payload))


def test_delegation_cannot_be_spoofed_with_unimported_module():
    payload, row = _candidate()
    row["backend_delegates"][0]["source"] = "frontend/src/features/discourse/unknown.ts"
    assert any("delegated backend source missing or unsafe" in item for item in _errors(payload))


def test_backend_mapping_and_declared_api_paths_are_not_waived():
    payload, row = _candidate()
    row["backend_mode"] = "local_or_navigation"
    assert any("backend mapping disagrees with source" in item for item in _errors(payload))
    payload, row = _candidate()
    row["backend_surfaces"] = []
    assert any("backend_surfaces drift" in item for item in _errors(payload))
