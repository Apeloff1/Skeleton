from __future__ import annotations

import copy
import hashlib
import json

import pytest

from skeleton.persistence.spine_bind_restore_export import SpineBindRestoreExport
from skeleton.persistence.spine_bind_restore_export_verify import (
    SpineBindRestoreExportVerify,
    SpineBindRestoreExportVerifyError,
)


TENANT = "tenant-portable-restore"


def _receipt():
    body = {
        "kind": "spine_bind_restore_receipt",
        "tenant_id": TENANT,
        "backup_restore_digest": "b" * 64,
        "recovery_digest": "a" * 64,
        "activated": False,
        "apply_landed": False,
        "live_motor": False,
        "dispatcher_running": False,
        "provider_surface_green": False,
        "pr_automation_green": False,
        "ci_green": False,
        "merged": False,
    }
    body["digest"] = "c" * 64
    return body


def _continuity():
    return {
        "kind": "spine_bind_restore_continuity",
        "tenant_id": TENANT,
        "receipt_digest": "c" * 64,
        "digest": "d" * 64,
        "journal_row_digest": "e" * 64,
        "chain_digest": "f" * 64,
        "durable": True,
        "tenant_isolated": True,
        "replay_safe": True,
        "activated": False,
        "apply_landed": False,
        "live_motor": False,
        "dispatcher_running": False,
        "provider_surface_green": False,
        "pr_automation_green": False,
        "ci_green": False,
        "merged": False,
    }


def test_portable_restore_export_is_deterministic_and_verified() -> None:
    exporter = SpineBindRestoreExport()
    first = exporter.card(receipt=_receipt(), continuity=_continuity())
    second = exporter.card(receipt=_receipt(), continuity=_continuity())

    assert first == second
    assert first["bytes"] == len(first["export_json"].encode("utf-8"))
    assert first["activated"] is False

    verified = SpineBindRestoreExportVerify().verify(first)
    assert verified["verified"] is True
    assert verified["export_digest"] == first["digest"]
    assert verified["activated"] is False
    assert verified["completion_checkbox"] is False

    payload = json.loads(first["export_json"])
    assert payload["durable"] is True
    assert payload["tenant_isolated"] is True
    assert payload["replay_safe"] is True
    assert payload["activated"] is False
    assert payload["completion_checkbox"] is False


def test_portable_restore_export_rejects_tampered_content() -> None:
    export = SpineBindRestoreExport().card(
        receipt=_receipt(),
        continuity=_continuity(),
    )
    tampered = copy.deepcopy(export)
    payload = json.loads(tampered["export_json"])
    payload["ci_green"] = True
    tampered["export_json"] = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    with pytest.raises(
        SpineBindRestoreExportVerifyError,
        match="export digest mismatch",
    ):
        SpineBindRestoreExportVerify().verify(tampered)


def test_portable_restore_export_rejects_noncanonical_json() -> None:
    export = SpineBindRestoreExport().card(
        receipt=_receipt(),
        continuity=_continuity(),
    )
    noncanonical = copy.deepcopy(export)
    payload = json.loads(noncanonical["export_json"])
    noncanonical["export_json"] = json.dumps(payload, sort_keys=True)
    noncanonical["digest"] = hashlib.sha256(
        noncanonical["export_json"].encode("utf-8")
    ).hexdigest()

    with pytest.raises(
        SpineBindRestoreExportVerifyError,
        match="not canonical",
    ):
        SpineBindRestoreExportVerify().verify(noncanonical)


def test_portable_restore_export_rejects_duplicate_json_keys() -> None:
    export = SpineBindRestoreExport().card(
        receipt=_receipt(),
        continuity=_continuity(),
    )
    duplicate = copy.deepcopy(export)
    duplicate["export_json"] = '{"kind":"spine_bind_restore_evidence","kind":"forged"}'
    duplicate["digest"] = hashlib.sha256(
        duplicate["export_json"].encode("utf-8")
    ).hexdigest()

    with pytest.raises(
        SpineBindRestoreExportVerifyError,
        match="export JSON is invalid",
    ):
        SpineBindRestoreExportVerify().verify(duplicate)
