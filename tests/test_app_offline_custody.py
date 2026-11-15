"""App-owned private custody and explicit provisioning regressions."""
import os
import sqlite3

import pytest

from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteUnavailable
from skeleton.app.offline_custody import open_academy_custody, open_work_custody
from skeleton.frontier.durable_work import WorkIntegrityError, WorkOrder, work_identity
from skeleton.learning.school.checkpoint_codec import AcademyState
from skeleton.learning.school.checkpoint_store import AcademyIntegrityError
from skeleton.learning.school.student import StudentProfile

pytestmark = pytest.mark.skipif(os.name != "posix", reason="private POSIX SQLite contract")


def work(path, create):
    return open_work_custody(path, scope="tenant", custody_key=b"w" * 32,
                             recovery_key=b"r" * 32, create=create)


def academy(path, create):
    return open_academy_custody(path, owner="tenant", key=b"a" * 32, create=create)


def test_explicit_provisioning_and_restart(tmp_path):
    tmp_path.chmod(0o700)
    with pytest.raises(OSError):
        with work(tmp_path, False):
            pass
    wid = work_identity("tenant", "test", "stable")
    with work(tmp_path, True) as (journal, _):
        journal.submit([WorkOrder(wid, "test", {"value": 1})])
    with academy(tmp_path, True) as store:
        receipt = store.save(AcademyState(StudentProfile("student", "Name")),
                             expected_revision=0, request_id="session")
    with work(tmp_path, False) as (journal, _):
        assert journal.status(wid).state == "pending"
    with academy(tmp_path, False) as store:
        assert store.load("student", trusted_head=receipt).receipt == receipt
    with pytest.raises(FileExistsError):
        with work(tmp_path, True):
            pass


@pytest.mark.parametrize(("filename", "opener", "error"), [
    ("frontier-work-orders.db", work, WorkIntegrityError),
    ("academy-checkpoints.db", academy, AcademyIntegrityError),
])
def test_reopen_does_not_bootstrap_missing_schema(tmp_path, filename, opener, error):
    tmp_path.chmod(0o700)
    path = tmp_path / filename
    db = sqlite3.connect(path)
    db.close()
    path.chmod(0o600)
    with pytest.raises(error):
        with opener(tmp_path, False):
            pass


def test_changed_permissions_fail_before_journal_operation(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "frontier-work-orders.db"
    with work(tmp_path, True) as (journal, _):
        path.chmod(0o644)
        try:
            with pytest.raises(PrivateSQLiteUnavailable):
                journal.list_status()
        finally:
            path.chmod(0o600)
