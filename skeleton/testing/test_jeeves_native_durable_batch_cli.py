"""Operator durable native batch CLI with REAL SQLite and SYNTHETIC model.

Only local native activation/installed model qualification is mocked.
All parser, multi-wave dispatch, replay, source identity, output receipt
and transaction protocols are production code paths.
"""
from __future__ import annotations

from contextlib import nullcontext
from io import BytesIO,TextIOWrapper,StringIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity,SpineLimits
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.agent.native_durable_batch_cli import run,parse_durable_jobs
from skeleton.jeeves.agent.native_durable_batch import NativeDurableBatchConveyor
from skeleton.testing.test_jeeves_native_sqlite_integration import MODEL,TOKENIZER,SyntheticallyGenerated


@unittest.skipUnless(os.name=="posix" and Path("/proc/self/fd").is_dir(),
                     "production SQLite must be supported")
class TestNativeDurableBatchOperatorCLI(unittest.TestCase):
    SECRET="Private task from operator, not process argv"
    BATCH="operator_batch_001"

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=None
        self.gate=None
        self._open()
        self.addCleanup(self._close)
        self.casebook={
            "schema":"jeeves.native_durable_casebook.v1",
            "batch_id":self.BATCH,
            "jobs":[
                {"task_id":"a","prompt":self.SECRET,
                 "priority":10,"cohort":"interactive"},
                {"task_id":"b","prompt":"Second independent operation.",
                 "priority":2,"cohort":"background"},
            ],
        }

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate=None
        if self.db is not None:
            self.db.close()
            self.db=None

    def _open(self,*,subject="operator"):
        self.db=SpineDatabase(self.temp.name)
        self.gate=SessionGate(self.temp.name)
        self.backend=SyntheticallyGenerated()
        self.spine=ExecutionSpine(
            db=self.db,session_gate=self.gate,backend=self.backend,
            identity=Identity("local",subject,MODEL,TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768,response_bytes=131072,
                max_output_tokens=128,context_tokens=4096,
            ),
        )
        self.worker=SupervisedAI(self.spine)

    def _cold(self,*,subject="operator"):
        self._close()
        self._open(subject=subject)

    def _invoke(self,mode="admit",*,book=None,raw=None,approved=True,
                stdin=True,extra=(),subject="operator"):
        if raw is None:
            raw=json.dumps(book if book is not None else self.casebook).encode()
        input_stream=TextIOWrapper(BytesIO(raw),encoding="utf-8")
        stdout,stderr=StringIO(),StringIO()
        argv=[
            "--mode",mode,"--model-root","/approved/mock",
            "--state-dir",self.temp.name,
            "--tenant","local","--subject",subject,
        ]
        if approved:
            argv.append("--approve-native")
        if stdin:
            argv.append("--casebook-stdin")
        argv.extend(extra)
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_durable_batch_cli.activate_checked",
                return_value=(nullcontext(),self.worker,object()),
            ) as startup,
            mock.patch(
                "skeleton.jeeves.agent.native_durable_batch_cli.inspect_native_jeeves",
                return_value=SimpleNamespace(source_bridge_ready=True),
            ),
            mock.patch("sys.stdin",input_stream),
            mock.patch("sys.stdout",stdout),
            mock.patch("sys.stderr",stderr),
        ):
            code=run(argv)
        return code,(json.loads(stdout.getvalue()) if stdout.getvalue() else None),stderr.getvalue(),startup.call_count

    def test_admission_stages_two_real_sqlite_work_orders_without_native_call(self):
        code,report,err,activated=self._invoke()
        self.assertEqual(code,0,err)
        self.assertEqual(report["total"],2)
        self.assertEqual(report["queued"],2)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(activated,1)

    def test_operator_cli_one_bounded_wave(self):
        self.assertEqual(self._invoke()[0],0)
        code,report,err,_=self._invoke("wave")
        self.assertEqual(code,0,err)
        self.assertEqual(report["processed"],1)
        self.assertEqual(report["status"]["committed"],1)
        self.assertEqual(self.backend.calls,1)

    def test_repeated_wave_completes_without_duplicate_native_effect(self):
        self._invoke()
        self._invoke("wave")
        self._invoke("wave")
        code,report,err,_=self._invoke("wave")
        self.assertEqual(code,0,err)
        self.assertEqual(report["processed"],0)
        self.assertEqual(self.backend.calls,2)
        self.assertTrue(report["status"]["fully_native_committed"])

    def test_cold_restart_cli_inspection_does_not_generate(self):
        self._invoke()
        self._invoke("wave")
        self._cold()
        code,report,err,_=self._invoke("inspect")
        self.assertEqual(code,0,err)
        self.assertEqual(report["committed"],1)
        self.assertEqual(report["queued"],1)
        self.assertEqual(self.backend.calls,0)

    def test_resume_only_remaining_queued_work_after_restart(self):
        self._invoke()
        self._invoke("wave")
        self._cold()
        code,report,err,_=self._invoke("wave")
        self.assertEqual(code,0,err)
        self.assertEqual(report["processed"],1)
        self.assertEqual(self.backend.calls,1)

    def test_duplicate_admit_does_not_regenerate(self):
        self._invoke()
        code,report,err,_=self._invoke()
        self.assertEqual(code,2)
        self.assertIsNone(report)
        self.assertIn("NativeDurableBatchHold",err)
        self.assertEqual(self.backend.calls,0)

    def test_casebook_priority_change_refused_before_native_effect(self):
        self._invoke()
        modified=json.loads(json.dumps(self.casebook))
        modified["jobs"][0]["priority"]=11
        code,report,err,_=self._invoke("wave",book=modified)
        self.assertEqual(code,2)
        self.assertIsNone(report)
        self.assertEqual(self.backend.calls,0)

    def test_casebook_task_content_change_refused(self):
        self._invoke()
        altered=json.loads(json.dumps(self.casebook))
        altered["jobs"][0]["prompt"]="Unapproved changed task"
        code,report,err,_=self._invoke("wave",book=altered)
        self.assertEqual(code,2)
        self.assertIsNone(report)
        self.assertEqual(self.backend.calls,0)
        self.assertNotIn("Unapproved changed task",err)

    def test_foreign_operator_cannot_view_existing_batch(self):
        self._invoke()
        self._cold(subject="foreign")
        code,report,err,_=self._invoke("inspect",subject="foreign")
        self.assertEqual(code,2)
        self.assertIsNone(report)
        self.assertEqual(self.backend.calls,0)

    def test_no_native_activation_without_explicit_approval(self):
        code,report,err,activated=self._invoke(approved=False)
        self.assertEqual(code,2)
        self.assertIsNone(report)
        self.assertEqual(activated,0)
        self.assertEqual(self.backend.calls,0)

    def test_no_model_activation_without_stdin_contract(self):
        code,report,err,activated=self._invoke(stdin=False)
        self.assertEqual(code,2)
        self.assertIsNone(report)
        self.assertEqual(activated,0)

    def test_strict_casebook_rejects_duplicate_field(self):
        raw=(b'{"schema":"jeeves.native_durable_casebook.v1",'
             b'"batch_id":"a","batch_id":"b","jobs":[]}')
        code,report,err,activated=self._invoke(raw=raw)
        self.assertEqual(code,2)
        self.assertEqual(activated,0)

    def test_strict_casebook_rejects_unknown_field(self):
        altered=dict(self.casebook)
        altered["automatic_retry"]=True
        code,report,err,activated=self._invoke(book=altered)
        self.assertEqual(code,2)
        self.assertEqual(activated,0)

    def test_operator_can_bound_one_wave_to_one_call(self):
        self._invoke()
        code,report,err,_=self._invoke("wave",extra=("--max-new-calls","1"))
        self.assertEqual(code,0,err)
        self.assertEqual(report["processed"],1)

    def test_invalid_wave_capacity_rejected_before_activation(self):
        code,report,err,activated=self._invoke(
            extra=("--max-new-calls","0"),
        )
        self.assertEqual(code,2)
        self.assertEqual(activated,0)

    def test_failed_wave_without_existing_admission_never_generates(self):
        code,report,err,_=self._invoke("wave")
        self.assertEqual(code,2)
        self.assertEqual(self.backend.calls,0)

    def test_no_private_task_disclosure_in_cli_report_or_error(self):
        self._invoke()
        code,report,err,_=self._invoke("inspect")
        self.assertEqual(code,0,err)
        self.assertNotIn(self.SECRET,str(report))
        self.assertNotIn(self.SECRET,err)
        self.assertFalse(report["release_certified"])

    def test_explicit_orphan_replay_finds_committed_native_turn_without_generation(self):
        self._invoke()
        runtime=NativeDurableBatchConveyor(self.worker,approved=True)
        order_id=runtime._order_key(self.BATCH,"a")
        claim=runtime.queue.claim(order_id)
        self.spine.create(claim.order.session_id)
        self.worker.turn(claim.order.session_id,claim.order.request_id,
                         self.SECRET,seed=0,temperature=0.8)
        self._cold()
        code,report,err,_=self._invoke("reconcile")
        self.assertEqual(code,0,err)
        self.assertEqual(report["reconciled"],1)
        self.assertEqual(report["model_calls_started"],0)
        self.assertEqual(self.backend.calls,0)


if __name__=="__main__":
    unittest.main()
