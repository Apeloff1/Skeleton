"""Authenticated report custody tamper, replay and SQLite reopen exercises."""
from __future__ import annotations
import sqlite3
import tempfile
from pathlib import Path
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.canonical import encode
from skeleton.ai.runtime.operational_ai.native_qualification.contracts import ModelIdentity
from skeleton.ai.runtime.operational_ai.native_qualification.policy import Threshold
from skeleton.ai.runtime.operational_ai.native_qualification.report import QualificationReport
from skeleton.ai.runtime.operational_ai.native_qualification.results import CaseResult
from skeleton.ai.runtime.operational_ai.native_qualification.report_ledger import ReportLedger
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


def report(run_id="run_1"):
    model = ModelIdentity("a"*64,"b"*64,"tenant","user","original","c"*64)
    return QualificationReport(
        run_id,model,"d"*64,
        (CaseResult("arithmetic_01","arithmetic","high","e"*64,(),"native-call-failed"),),
        "2026-11-03T09:00:00+00:00", "2026-11-03T09:00:01+00:00",
        False,False,False,Threshold(),
    )


class TestNativeReportLedger(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.file = Path(self.temp.name) / "reports.sqlite"
        self.key = b"K" * 32

    def tearDown(self):
        self.temp.cleanup()

    def test_source_digest_and_replay(self):
        with sqlite3.connect(self.file,isolation_level=None) as db:
            store = ReportLedger(db,mac_key=self.key)
            data=encode(report().record())
            first=store.append(scope="tenant",run_id="run_1",report_bytes=data)
            self.assertEqual(first["status"],"recorded")
            again=store.append(scope="tenant",run_id="run_1",report_bytes=data)
            self.assertEqual(again["status"],"replayed")
            self.assertEqual(store.verify("tenant")["entries"],1)

    def test_persistent_ledger_on_reopen(self):
        with sqlite3.connect(self.file,isolation_level=None) as db:
            ReportLedger(db,mac_key=self.key).append(
                scope="tenant",run_id="run_1",report_bytes=encode(report().record())
            )
        with sqlite3.connect(self.file,isolation_level=None) as db:
            store = ReportLedger(db,mac_key=self.key)
            self.assertTrue(store.verify("tenant")["verified"])
            store.append(scope="tenant",run_id="run_2",report_bytes=encode(report("run_2").record()))
            self.assertEqual(store.verify("tenant")["entries"],2)

    def test_tampered_blob_rejected(self):
        with sqlite3.connect(self.file,isolation_level=None) as db:
            store = ReportLedger(db,mac_key=self.key)
            store.append(scope="tenant",run_id="run_1",report_bytes=encode(report().record()))
            db.execute("UPDATE qualification_report_ledger SET report_bytes=? WHERE scope='tenant'",
                       (b"{}",))
            with self.assertRaises(QualificationError):
                store.verify("tenant")

    def test_wrong_mac_key_rejected(self):
        with sqlite3.connect(self.file,isolation_level=None) as db:
            ReportLedger(db,mac_key=self.key).append(
                scope="tenant",run_id="run_1",report_bytes=encode(report().record())
            )
            with self.assertRaises(QualificationError):
                ReportLedger(db,mac_key=b"Z"*32).verify("tenant")


if __name__ == "__main__":
    unittest.main()
