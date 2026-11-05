"""Native batch CLI: pure admission, installed lease and bounded publication.

Every model, installer and SQLite runner here is mocked. These tests cannot
qualify real GGUF rights, device pressure, native output or consumer release.
"""
from __future__ import annotations

from contextlib import nullcontext, redirect_stdout, redirect_stderr
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_batch_cli import main, parse_casebook
from skeleton.jeeves.agent.native_batch_runtime import NativeBatchHold
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256":"c"*64, "archive_sha256":"d"*64,
    "source_sha":"e"*40, "installed_model_bytes":2048,
    "installed_shard_count":1,
}


def casebook(task="private original work"):
    return json.dumps({
        "schema":"jeeves.native_batch_casebook.v1",
        "batch_id":"approved_batch_1",
        "tasks":[{"task_id":"task_1","prompt":task}],
    }).encode("utf8")


def args(*extra):
    return [
        "--model-root","/private/installed_gguf",
        "--state-dir","/private/sqlite",
        "--tenant","local","--subject","owner",
        "--batch-stdin","--approve-native",*extra,
    ]


class IncompleteOutput(StringIO):
    def write(self, text):
        super().write(text[:4])
        return 4


def execute(
    argv=None, *, raw=None, worker=None, source=SOURCE, output=None,
    report=None, during_run=None,
):
    worker = worker or FakeWorker()
    stdin = SimpleNamespace(buffer=BytesIO(casebook() if raw is None else raw))
    stdout = output if output is not None else StringIO()
    stderr = StringIO()
    batch = mock.Mock()
    batch.run.return_value.to_public_record.return_value = (
        report if report is not None else {
            "schema":"jeeves.native_batch_result.v1",
            "status":"committed",
            "committed_jobs":1,
            "device_qualified":False,
            "release_certified":False,
        }
    )
    if during_run is not None:
        def run_with_revocation(*args, **kwargs):
            during_run(worker)
            return batch.run.return_value
        batch.run.side_effect = run_with_revocation
    with (
        mock.patch("skeleton.jeeves.agent.native_batch_cli.sys.stdin",stdin),
        mock.patch("skeleton.jeeves.agent.native_batch_cli.sys.stdout",stdout),
        mock.patch("skeleton.jeeves.agent.native_batch_cli.sys.stderr",stderr),
        mock.patch(
            "skeleton.jeeves.agent.native_batch_cli.activate_checked",
            return_value=(nullcontext(),worker,object()),
        ) as native,
        mock.patch(
            "skeleton.jeeves.agent.native_batch_cli.inspect_native_jeeves",
            return_value=SimpleNamespace(source_bridge_ready=True),
        ) as readiness,
        mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(source) if type(source) is dict else source,
        ) as witness,
        mock.patch(
            "skeleton.jeeves.agent.native_batch_cli.NativeBatchConveyor",
            return_value=batch,
        ) as constructor,
    ):
        status=main(args() if argv is None else argv)
    return status,stdout.getvalue(),stderr.getvalue(),stdin,native,readiness,witness,constructor,batch,worker


class NativeBatchOperatorBoundaryTests(unittest.TestCase):
    def test_approved_single_batch_runs_only_one_real_spine_lane(self):
        code,out,err,stdin,native,ready,source,conveyor,batch,worker=execute()
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["status"],"committed")
        self.assertEqual(json.loads(out)["committed_jobs"],1)
        self.assertNotIn("private original work",out)
        self.assertNotIn("private original work",err)
        native.assert_called_once()
        conveyor.assert_called_once()
        batch.run.assert_called_once()
        self.assertGreaterEqual(source.call_count,5)
        self.assertEqual(worker.generation_calls,0)

    def test_unapproved_batch_never_reads_private_stdin_or_loads_model(self):
        argv=[x for x in args() if x != "--approve-native"]
        code,out,err,stdin,native,*_=execute(argv)
        self.assertEqual(code,2)
        self.assertEqual(stdin.buffer.tell(),0)
        native.assert_not_called()
        self.assertEqual(out,"")
        self.assertIn('"status": "held"',err)

    def test_bad_private_path_never_enters_source_inspector(self):
        for flag,value in (
            ("--model-root","relative.gguf"),
            ("--state-dir","/root/../escape"),
            ("--capacity-root","../private"),
        ):
            with self.subTest(flag=flag):
                result=execute(args(flag,value))
                self.assertEqual(result[0],2)
                self.assertEqual(result[3].buffer.tell(),0)
                result[4].assert_not_called()
                self.assertNotIn(value,result[2])

    def test_invalid_native_shape_before_task_bytes(self):
        for flag,value in (
            ("--context","1"),("--max-new-tokens","100000"),
            ("--threads","0"),("--gpu-layers","-1"),
            ("--capacity-budget-bytes","0"),
            ("--maximum-jobs","0"),
            ("--maximum-wall-seconds","nan"),
        ):
            with self.subTest(flag=flag):
                result=execute(args(flag,value))
                self.assertEqual(result[0],2)
                self.assertEqual(result[3].buffer.tell(),0)
                result[4].assert_not_called()

    def test_argparse_redacts_unknown_flag_and_secret(self):
        private="private-user-token-do-not-log"
        code,out,err,stdin,native,*_=execute(
            args("--unknown-private-flag",private)
        )
        self.assertEqual(code,2)
        self.assertEqual(out,"")
        self.assertNotIn(private,err)
        self.assertNotIn("usage:",err)
        self.assertEqual(stdin.buffer.tell(),0)
        native.assert_not_called()

    def test_invalid_tenant_before_private_read(self):
        result=execute(args("--tenant","bad/owner"))
        self.assertEqual(result[0],2)
        self.assertEqual(result[3].buffer.tell(),0)
        result[4].assert_not_called()

    def test_source_inspector_denies_wrong_model_before_generation(self):
        invalid={**SOURCE,"model_sha256":"f"*64}
        code,out,err,stdin,native,ready,witness,constructor,batch,worker=execute(
            source=invalid,
        )
        self.assertEqual(code,2)
        self.assertEqual(out,"")
        constructor.assert_not_called()
        batch.run.assert_not_called()
        self.assertIn('"status": "held"',err)
        self.assertEqual(worker.generation_calls,0)

    def test_installed_rights_not_approved_blocks_all_batch_work(self):
        code,out,err,stdin,native,ready,witness,constructor,batch,worker=execute(
            source=ContractlessSource(),
        )
        self.assertEqual(code,2)
        constructor.assert_not_called()
        batch.run.assert_not_called()
        self.assertEqual(worker.generation_calls,0)

    def test_casebook_bound_enforced_before_native_startup(self):
        result=execute(raw=b"x"*1048577)
        self.assertEqual(result[0],2)
        result[4].assert_not_called()
        self.assertEqual(result[1],"")
        self.assertNotIn("x"*100,result[2])

    def test_casebook_unknown_keys_denied_before_activation(self):
        body=json.loads(casebook())
        body["automatic_retry"]=True
        result=execute(raw=json.dumps(body).encode())
        self.assertEqual(result[0],2)
        result[4].assert_not_called()

    def test_distinct_task_identity_reused_is_held(self):
        body=json.loads(casebook())
        body["tasks"]=[body["tasks"][0],body["tasks"][0]]
        result=execute(raw=json.dumps(body).encode())
        self.assertEqual(result[0],2)
        result[4].assert_not_called()

    def test_short_batch_stdout_is_held_not_acknowledged(self):
        code,out,err,stdin,native,ready,witness,constructor,batch,worker=execute(
            output=IncompleteOutput(),
        )
        self.assertEqual(code,2)
        self.assertEqual(len(out),4)
        batch.run.assert_called_once()
        self.assertEqual(worker.generation_calls,0)
        self.assertIn('"status": "held"',err)

    def test_batch_result_nonfinite_json_refused_without_stdout(self):
        worker = FakeWorker()
        report = {
            "schema":"jeeves.native_batch_result.v1",
            "answer":float("nan"),
        }
        status,out,err,_,_,_,_,_,batch,_ = execute(
            worker=worker,report=report,
        )
        self.assertEqual(status,2)
        self.assertEqual(out,"")
        self.assertIn('"status": "held"',err)
        batch.run.assert_called_once()
        self.assertEqual(worker.generation_calls,0)

    def test_source_revoked_after_native_batch_blocks_public_ack(self):
        def change_model(worker):
            worker.spine.backend.model_digest="f"*64
        result = execute(during_run=change_model)
        status,out,err,stdin,native,ready,witness,constructor,batch,worker = result
        self.assertEqual(status,2)
        self.assertEqual(out,"")
        self.assertIn('"status": "held"',err)
        batch.run.assert_called_once()
        self.assertEqual(worker.generation_calls,0)

    def test_oversized_response_record_fails_without_partial_stdout(self):
        report = {
            "schema":"jeeves.native_batch_result.v1",
            "debug":"PRIVATE"*750000,
        }
        result=execute(report=report)
        self.assertEqual(result[0],2)
        self.assertEqual(result[1],"")
        self.assertNotIn("PRIVATE",result[2])
        result[8].run.assert_called_once()

    def test_parser_rejects_malformed_casebooks_without_carrying_task(self):
        for blob in (b"",b"{",b"[]",b"null",b'{"schema":false}',b" "*1048577):
            with self.subTest(blob=blob[:20]),self.assertRaises(Exception):
                parse_casebook(blob)


class ContractlessSource:
    """Deliberately wrong installed source witness shape."""


if __name__=="__main__":
    unittest.main()
