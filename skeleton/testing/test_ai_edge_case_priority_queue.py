from __future__ import annotations

import json

from scripts import check_ai_edge_case_priority_queue as checker


def _payloads():
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    catalog = json.loads(checker.CATALOG.read_text(encoding="utf-8"))
    return queue, catalog


def test_edge_case_priority_queue_is_valid() -> None:
    assert checker.validate() == []


def test_priority_queue_rejects_missing_critical_catalog_entry() -> None:
    queue, catalog = _payloads()
    mutated = json.loads(json.dumps(queue))
    mutated["items"].pop()

    errors = checker.validate(mutated, catalog)

    assert (
        "priority queue must contain every critical/high catalog entry exactly once"
        in errors
    )


def test_priority_queue_rejects_noncontiguous_rank() -> None:
    queue, catalog = _payloads()
    mutated = json.loads(json.dumps(queue))
    mutated["items"][0]["rank"] = 2

    errors = checker.validate(mutated, catalog)

    assert "priority queue ranks must be contiguous and ordered from 1" in errors


def test_priority_queue_rejects_catalog_metadata_drift() -> None:
    queue, catalog = _payloads()
    mutated = json.loads(json.dumps(queue))
    item_id = mutated["items"][0]["id"]
    mutated["items"][0]["work_package_refs"] = ["WP-W30"]

    errors = checker.validate(mutated, catalog)

    assert f"{item_id}: work_package_refs drifted from source catalog" in errors


def test_evidence_pending_requires_real_evidence_refs() -> None:
    queue, catalog = _payloads()
    mutated = json.loads(json.dumps(queue))
    item = next(x for x in mutated["items"] if x["status"] == "evidence_pending")
    item["evidence"] = []

    errors = checker.validate(mutated, catalog)

    assert f"{item['id']}: evidence_pending item needs evidence refs" in errors


def test_planned_item_cannot_claim_evidence() -> None:
    queue, catalog = _payloads()
    mutated = json.loads(json.dumps(queue))
    item = next(x for x in mutated["items"] if x["status"] == "planned")
    item["evidence"] = ["test:fake"]

    errors = checker.validate(mutated, catalog)

    assert f"{item['id']}: planned item cannot claim evidence" in errors


def test_queued_evidence_is_pending_not_signed_off() -> None:
    queue, catalog = _payloads()
    pending = [item for item in queue["items"] if item["status"] == "evidence_pending"]
    planned = [item for item in queue["items"] if item["status"] == "planned"]

    assert pending and planned
    assert all(item["evidence"] and item["disposition"] for item in pending)
    assert all(not item["evidence"] and item["disposition"] is None for item in planned)
    assert all(
        not item["completion_checkbox"]
        and item["completion_checkbox_mark"] == "[ ]"
        and item["accountability_status"] == item["status"]
        for item in queue["items"]
    )
    assert checker.validate(queue, catalog) == []


def test_planned_or_evidence_pending_cannot_prematurely_claim_verification() -> None:
    queue, catalog = _payloads()
    for status in ("planned", "evidence_pending"):
        mutated = json.loads(json.dumps(queue))
        item = next(row for row in mutated["items"] if row["status"] == status)
        item["completion_checkbox"] = True
        item["completion_checkbox_mark"] = "[x]"
        item["accountability_status"] = "verified"
        errors = checker.validate(mutated, catalog)
        assert f"{item['id']}: unverified item cannot claim completion" in errors
        assert f"{item['id']}: unverified item cannot claim verified accountability" in errors
