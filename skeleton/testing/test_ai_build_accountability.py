from __future__ import annotations

import json

from scripts import check_ai_build_accountability as checker


def _load() -> dict:
    return json.loads(checker.LEDGER.read_text(encoding="utf-8"))


def test_accountability_ledger_is_valid() -> None:
    assert checker.validate() == []


def test_accountability_tracks_every_plan_build_surface() -> None:
    ledger = _load()
    master = json.loads(checker.MASTER.read_text(encoding="utf-8"))
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    p1 = json.loads(checker.P1.read_text(encoding="utf-8"))
    catalog = json.loads(checker.CATALOG.read_text(encoding="utf-8"))
    assert ledger["tracked_counts"] == {
        "volumes": 421,
        "work_packages": 31,
        "queue_tasks": len(queue["tasks"]),
        "vertical_slices": len(master["vertical_slices"]),
        "catalog_entries": len(catalog["entries"]),
        "p1_tasks": len(p1["tasks"]),
        "total": (
            421
            + 31
            + len(queue["tasks"])
            + len(p1["tasks"])
            + len(master["vertical_slices"])
            + len(catalog["entries"])
        ),
    }
    assert all(record["signing_required"] is True for record in ledger["records"])


def test_no_completion_checkbox_is_checked_without_two_signoffs() -> None:
    ledger = _load()
    for record in ledger["records"]:
        if record["checkbox"]:
            assert record["implementation_signoff"]["signed"] is True
            assert record["verification_signoff"]["signed"] is True
            assert record["completed_at_utc"]


def test_current_pending_queue_has_no_fabricated_signatures() -> None:
    ledger = _load()
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    by_id = {record["id"]: record for record in ledger["records"]}
    for task in queue["tasks"]:
        if task["status"] == "pending":
            record = by_id[task["accountability_id"]]
            assert record["checkbox"] is False
            assert record["implementation_signoff"]["signed"] is False
            assert record["verification_signoff"]["signed"] is False


def test_visible_checkboxes_match_machine_ledger() -> None:
    ledger = _load()
    visible = {
        rid: mark
        for mark, rid in checker.CHECK_RE.findall(checker.HUMAN.read_text(encoding="utf-8"))
    }
    assert len(visible) == len(ledger["records"])
    for record in ledger["records"]:
        assert visible[record["id"]] == ("x" if record["checkbox"] else " ")


def test_every_catalog_obligation_is_accountability_tracked() -> None:
    ledger = _load()
    catalog = json.loads(checker.CATALOG.read_text(encoding="utf-8"))
    records = {record["id"]: record for record in ledger["records"]}
    assert len(catalog["entries"]) == 240
    for entry in catalog["entries"]:
        record = records[entry["accountability_id"]]
        assert entry["signing_required"] is True
        assert entry["completion_checkbox"] == record["checkbox"]
        assert entry["completion_checkbox_mark"] == record["checkbox_mark"]


def test_status_changes_require_signed_attributed_history_schema() -> None:
    ledger = _load()
    for record in ledger["records"]:
        if record["status"] != record["baseline_status"]:
            assert record["history"]
        for event in record["history"]:
            assert event["actor_id"]
            assert event["actor_type"] in checker.ALLOWED_SIGNER_TYPES
            assert event["role"]
            assert event["statement"]
            assert event["signature_method"] in checker.ALLOWED_SIGNATURE_METHODS
            assert checker.SHA_RE.fullmatch(event["git_sha"])
            assert checker._utc(event["at_utc"]) is not None
            assert "from_status" in event
            assert "to_status" in event


def test_manual_unbound_attestation_is_not_allowed() -> None:
    assert "manual_attestation" not in checker.ALLOWED_SIGNATURE_METHODS
    assert {"github_identity", "git_gpg", "git_ssh", "sigstore", "ci_oidc"} <= (
        checker.ALLOWED_SIGNATURE_METHODS
    )


def test_checkbox_regex_matches_literal_markdown_checkbox_lines() -> None:
    sample = "- [ ] `ACC-VOL-000` — volume\n- [x] `ACC-AIQ-X` — task\n"
    assert checker.CHECK_RE.findall(sample) == [
        (" ", "ACC-VOL-000"),
        ("x", "ACC-AIQ-X"),
    ]

def test_accountability_rejects_verification_before_implementation() -> None:
    record = {
        "started_at_utc": "2026-10-03T18:00:00Z",
        "completed_at_utc": "2026-10-03T19:00:00Z",
        "implementation_signoff": {
            "signed": True,
            "signed_at_utc": "2026-10-03T18:30:00Z",
        },
        "verification_signoff": {
            "signed": True,
            "signed_at_utc": "2026-10-03T18:20:00Z",
        },
    }

    errors = checker._timeline_errors("ACC-TEST", record)

    assert (
        "ACC-TEST: verification signoff predates implementation signoff"
        in errors
    )


def test_accountability_rejects_completion_before_verification() -> None:
    record = {
        "started_at_utc": "2026-10-03T18:00:00Z",
        "completed_at_utc": "2026-10-03T18:40:00Z",
        "implementation_signoff": {
            "signed": True,
            "signed_at_utc": "2026-10-03T18:20:00Z",
        },
        "verification_signoff": {
            "signed": True,
            "signed_at_utc": "2026-10-03T18:45:00Z",
        },
    }

    errors = checker._timeline_errors("ACC-TEST", record)

    assert "ACC-TEST: completed_at_utc predates verification signoff" in errors

