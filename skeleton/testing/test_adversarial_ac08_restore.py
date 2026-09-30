from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Record:
    value: str
    deleted: bool = False
    credential_valid: bool = True


def delete(record: Record) -> None:
    record.deleted = True


def restore(record: Record) -> None:
    record.deleted = False


def reconcile_external(record: Record, external_deleted: bool) -> None:
    record.deleted = external_deleted


def revalidate_credential(record: Record, valid: bool) -> None:
    record.credential_valid = valid


def test_restore_drill_does_not_resurrect_external_deletion():
    record = Record("payload")
    delete(record)
    restore(record)
    reconcile_external(record, external_deleted=True)
    assert record.deleted is True


def test_restore_revalidates_credentials_before_use():
    record = Record("payload", deleted=True, credential_valid=False)
    restore(record)
    revalidate_credential(record, valid=False)
    assert record.credential_valid is False


def test_restore_preserves_data_when_external_state_allows_it():
    record = Record("payload", deleted=True)
    restore(record)
    reconcile_external(record, external_deleted=False)
    assert record.deleted is False
    assert record.value == "payload"
