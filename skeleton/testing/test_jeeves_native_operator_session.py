"""Operator-owned durable multi-run terminal with actual protected SQLite.

Native token generation is a SYNTHETIC model-shaped adapter. All run custody,
planner/source guards, WAL transactions, terminal receipts, cold replay,
operator task binding, and command stream handling are production code.
"""
from __future__ import annotations

from contextlib import nullcontext
from io import BytesIO,StringIO,TextIOWrapper
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity,SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.agent.native_operator_session import (
    NativeOperatorSession,NativeOperatorSessionHold,OperatorCommand,
    OperatorSessionLimits,parse_operator_command,
)
from skeleton.jeeves.agent.native_operator_session_cli import main as cli_main
from skeleton.jeeves.agent.native_durable_runtime import NativeDurableJeevesAgent
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL,TOKENIZER,ScriptedAgentBackend,
)


@unittest.skipUnless(os.name=="posix" and Path("/proc/self/fd").is_dir(),
                     "protected native SQLite requires Linux /proc")
class TestDurableOperatorSession(unittest.TestCase):
    TASK="Privately reason about offline Jeeves without network."

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=None
        self.gate=None
        self._open()
        self.addCleanup(self._close)

    def _open(self,*,subject="operator"):
        self.db=SpineDatabase(self.tmp.name)
        self.gate=SessionGate(self.tmp.name)
        self.backend=ScriptedAgentBackend()
        self.worker=SupervisedAI(ExecutionSpine(
            db=self.db,session_gate=self.gate,backend=self.backend,
            identity=Identity("local",subject,MODEL,TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768,response_bytes=131072,
                max_output_tokens=128,context_tokens=4096,
            ),
        ))
        self.session=NativeOperatorSession(self.worker,approved=True)

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate=None
        if self.db is not None:
            self.db.close()
            self.db=None

    def _cold(self,*,subject="operator"):
        self._close()
        self._open(subject=subject)

    def _command(self,operation="start",*,run_id="operator_run_one",task=None,
                 max_steps=8,max_model_calls=8,max_wall_seconds=180):
        if operation in ("quit","status"):
            return OperatorCommand(operation)
        return OperatorCommand(
            operation=operation,run_id=run_id,
            task=self.TASK if task is None else task,
            max_steps=max_steps,max_model_calls=max_model_calls,
            max_wall_seconds=max_wall_seconds,
        )

    def _lines(self,*commands):
        return b"".join(json.dumps({
            "schema":"jeeves.native_operator_command.v1",
            "operation":c.operation,
            **({"run_id":c.run_id,"task":c.task,
                "max_steps":c.max_steps,
                "max_model_calls":c.max_model_calls,
                "max_wall_seconds":c.max_wall_seconds}
               if c.operation not in ("quit","status") else {}),
        }).encode()+b"\n" for c in commands)

    def test_status_does_not_start_native_generation(self):
        result=self.session.dispatch(self._command("status"))
        self.assertEqual(result["run_count"],0)
        self.assertEqual(result["reserved_model_calls"],0)
        self.assertFalse(result["release_certified"])
        self.assertEqual(self.backend.calls,0)

    def test_one_operator_run_uses_strict_agent_three_native_sqlite_commits(self):
        result=self.session.dispatch(self._command())
        self.assertTrue(result["success"])
        self.assertEqual(result["answer"],"Local synthetic reasoning completed.")
        self.assertEqual(result["usage"]["model_calls"],3)
        self.assertEqual(self.backend.calls,3)
        self.assertEqual(result["native_model_sha256"],MODEL)
        self.assertEqual(result["native_tokenizer_sha256"],TOKENIZER)
        self.assertFalse(result["real_hardware_qualified"])
        self.assertFalse(result["release_certified"])
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone(),(3,))
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_terminal_results",
            ).fetchone(),(1,))

    def test_multiple_distinct_runs_reuse_same_loaded_supervisor(self):
        first=self.session.dispatch(self._command())
        second=self.session.dispatch(
            self._command(run_id="operator_run_two",task="Second local task."),
        )
        self.assertTrue(first["success"] and second["success"])
        self.assertEqual(self.backend.calls,6)
        self.assertEqual(self.session.dispatch(self._command("status"))["run_count"],2)

    def test_replay_is_readonly_and_does_not_generate_again(self):
        first=self.session.dispatch(self._command())
        saved=self.session.dispatch(self._command("replay"))
        self.assertEqual(saved["answer"],first["answer"])
        self.assertTrue(saved["replayed"])
        self.assertEqual(self.backend.calls,3)

    def test_inspect_is_readonly_and_excludes_private_task_bytes(self):
        self.session.dispatch(self._command())
        inspected=self.session.dispatch(self._command("inspect"))
        self.assertEqual(inspected["phase"],"completed")
        self.assertFalse(inspected["operator_resume_structurally_admissible"])
        self.assertNotIn(self.TASK,str(inspected))
        self.assertEqual(self.backend.calls,3)

    def test_cold_reopen_replays_terminal_result_without_native_generation(self):
        first=self.session.dispatch(self._command())
        self._cold()
        replay=self.session.dispatch(self._command("replay"))
        self.assertEqual(replay["answer"],first["answer"])
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(self.session.dispatch(self._command("status"))["run_count"],1)

    def test_changed_task_reusing_run_id_is_refused(self):
        self.session.dispatch(self._command())
        with self.assertRaises(Exception):
            self.session.dispatch(self._command(
                "replay",task="New unrelated prompt."
            ))
        self.assertEqual(self.backend.calls,3)

    def test_duplicate_start_after_terminal_commit_is_never_reexecuted(self):
        self.session.dispatch(self._command())
        with self.assertRaises(Exception):
            self.session.dispatch(self._command())
        self.assertEqual(self.backend.calls,3)

    def test_completed_run_cannot_be_explicitly_resumed(self):
        self.session.dispatch(self._command())
        with self.assertRaises(Exception):
            self.session.dispatch(self._command("resume"))
        self.assertEqual(self.backend.calls,3)

    def test_cold_operator_approved_resume_from_preinference_interrupt(self):
        runner=NativeDurableJeevesAgent(self.worker)
        inputs=self.session._inputs(self._command())
        with mock.patch.object(
            runner.agent.agent,"_plan",side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run(inputs)
        self.assertEqual(self.backend.calls,0)
        self._cold()
        resumed=self.session.dispatch(self._command("resume"))
        self.assertTrue(resumed["success"])
        self.assertEqual(self.backend.calls,3)

    def test_global_reserved_model_call_budget_blocks_second_run(self):
        self.session=NativeOperatorSession(
            self.worker,approved=True,
            limits=OperatorSessionLimits(
                maximum_reserved_model_calls=8,
                maximum_reserved_output_tokens=1024,
            ),
        )
        self.session.dispatch(self._command(max_model_calls=8))
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(self._command(
                run_id="run_two",task="More",max_model_calls=8,
            ))
        self.assertEqual(self.backend.calls,3)

    def test_single_call_budget_ceiling_rejects_before_model_generation(self):
        self.session=NativeOperatorSession(
            self.worker,approved=True,
            limits=OperatorSessionLimits(maximum_reserved_output_tokens=256),
        )
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(self._command(max_model_calls=8))
        self.assertEqual(self.backend.calls,0)

    def test_status_reads_exact_model_digest_and_no_hidden_model_call(self):
        report=self.session.dispatch(self._command("status"))
        self.assertEqual(report["installed_model_sha256"],MODEL)
        self.assertEqual(report["tokenizer_sha256"],TOKENIZER)
        self.assertFalse(report["actual_model_forward_pass_by_status"])
        self.assertEqual(self.backend.calls,0)

    def test_quit_refuses_future_commands(self):
        result=self.session.dispatch(self._command("quit"))
        self.assertEqual(result["status"],"closed")
        with self.assertRaises(NativeOperatorSessionHold):
            self.session.dispatch(self._command("status"))

    def test_stream_accepts_start_replay_inspect_then_quit(self):
        raw=self._lines(
            self._command(),self._command("replay"),
            self._command("inspect"),self._command("quit"),
        )
        output=StringIO()
        code=self.session.serve(BytesIO(raw),output)
        self.assertEqual(code,0)
        lines=[json.loads(v) for v in output.getvalue().splitlines()]
        self.assertEqual(len(lines),4)
        self.assertTrue(lines[0]["success"])
        self.assertEqual(lines[1]["answer"],lines[0]["answer"])
        self.assertEqual(lines[2]["phase"],"completed")
        self.assertEqual(lines[3]["status"],"closed")
        self.assertEqual(self.backend.calls,3)

    def test_stream_invalid_command_stops_without_private_error(self):
        raw=b'{"schema":"jeeves.native_operator_command.v1","operation":"start",'
        output=StringIO()
        code=self.session.serve(BytesIO(raw+b"\n"),output)
        self.assertEqual(code,2)
        self.assertNotIn("Privately",output.getvalue())
        self.assertIn("NativeOperatorSessionHold",output.getvalue())
        self.assertEqual(self.backend.calls,0)

    def test_oversized_line_does_not_load_model_or_disclose_bytes(self):
        source=BytesIO(b"x"*32769+b"\n")
        output=StringIO()
        code=self.session.serve(source,output)
        self.assertEqual(code,2)
        self.assertNotIn("xxxxx",output.getvalue())
        self.assertEqual(self.backend.calls,0)

    def test_unterminated_command_is_invalid(self):
        output=StringIO()
        code=self.session.serve(BytesIO(self._lines(self._command())[:-1]),output)
        self.assertEqual(code,2)
        self.assertEqual(self.backend.calls,0)

    def test_model_epoch_mismatch_or_foreign_scope_refuses_resume(self):
        self.session.dispatch(self._command())
        self._cold(subject="foreign")
        with self.assertRaises(Exception):
            self.session.dispatch(self._command("replay"))
        self.assertEqual(self.backend.calls,0)

    def test_strict_parser_rejects_duplicate_key(self):
        raw=(b'{"schema":"jeeves.native_operator_command.v1",'
             b'"operation":"start","operation":"quit"}')
        with self.assertRaises(NativeOperatorSessionHold):
            parse_operator_command(raw)

    def test_strict_parser_rejects_unknown_operator_grant(self):
        raw=json.dumps({
            "schema":"jeeves.native_operator_command.v1",
            "operation":"start","run_id":"run_one","task":"Hello",
            "grant":"shell_exec",
        }).encode()
        with self.assertRaises(NativeOperatorSessionHold):
            parse_operator_command(raw)

    def test_strict_parser_rejects_private_paths_in_control(self):
        raw=json.dumps({
            "schema":"jeeves.native_operator_command.v1",
            "operation":"status","task":"secret",
        }).encode()
        with self.assertRaises(NativeOperatorSessionHold):
            parse_operator_command(raw)

    def test_bool_model_call_budget_does_not_pass_integer_admission(self):
        with self.assertRaises(Exception):
            OperatorCommand("start",run_id="run_a",task="Hello",max_model_calls=True)

    def test_nonfinite_duration_budget_is_refused(self):
        for bad in (float("nan"),float("inf"),-1,True):
            with self.subTest(bad=bad),self.assertRaises(Exception):
                OperatorCommand(
                    "start",run_id="run_a",task="Hello",max_wall_seconds=bad,
                )

    def test_session_requires_explicit_operator_approval(self):
        with self.assertRaises(NativeOperatorSessionHold):
            NativeOperatorSession(self.worker,approved=False)

    def test_cli_refuses_missing_approval_before_activation_or_private_stdin(self):
        stdout,stderr=StringIO(),StringIO()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.activate_checked",
            ) as start,
            mock.patch("sys.stdout",stdout),mock.patch("sys.stderr",stderr),
        ):
            code=cli_main([
                "--model-root","/private/model","--state-dir",self.tmp.name,
                "--tenant","local","--subject","operator","--commands-stdin",
            ])
        self.assertEqual(code,2)
        start.assert_not_called()
        self.assertFalse(stdout.getvalue())

    def test_cli_uses_approved_source_bootstrap_and_real_session_protocol(self):
        stdout,stderr=StringIO(),StringIO()
        raw=self._lines(self._command(),self._command("quit"))
        stdin=TextIOWrapper(BytesIO(raw),encoding="utf-8")
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.activate_checked",
                return_value=(nullcontext(),self.worker,object()),
            ) as activate,
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.inspect_native_jeeves",
                return_value=SimpleNamespace(source_bridge_ready=True),
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value={
                    "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
                    "manifest_sha256":"c"*64,"archive_sha256":"d"*64,
                    "source_sha":"e"*40,"installed_model_bytes":2048,
                    "installed_shard_count":1,
                },
            ),
            mock.patch("sys.stdin",stdin),mock.patch("sys.stdout",stdout),
            mock.patch("sys.stderr",stderr),
        ):
            code=cli_main([
                "--model-root","/private/model","--state-dir",self.tmp.name,
                "--tenant","local","--subject","operator",
                "--commands-stdin","--approve-native",
                "--max-output-tokens","128",
            ])
        self.assertEqual(code,0,stderr.getvalue())
        self.assertEqual(activate.call_count,1)
        self.assertEqual(self.backend.calls,3)
        self.assertEqual(len(stdout.getvalue().splitlines()),2)
        self.assertNotIn(self.TASK,stderr.getvalue())

    def test_cli_holds_source_readiness_without_generating(self):
        stdout,stderr=StringIO(),StringIO()
        stdin=TextIOWrapper(BytesIO(self._lines(self._command())),encoding="utf-8")
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.activate_checked",
                return_value=(nullcontext(),self.worker,object()),
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.inspect_native_jeeves",
                return_value=SimpleNamespace(source_bridge_ready=False),
            ),
            mock.patch("sys.stdin",stdin),mock.patch("sys.stdout",stdout),
            mock.patch("sys.stderr",stderr),
        ):
            code=cli_main([
                "--model-root","/private/model","--state-dir",self.tmp.name,
                "--tenant","local","--subject","operator",
                "--commands-stdin","--approve-native",
            ])
        self.assertEqual(code,2)
        self.assertEqual(self.backend.calls,0)
        self.assertFalse(stdout.getvalue())


if __name__=="__main__":
    unittest.main()
