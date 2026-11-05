"""Operator observability, immutable canary holds, and telemetry regression."""
from __future__ import annotations
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
from pathlib import Path
import http.client
import json
import threading
import time
import unittest
from unittest.mock import patch

from skeleton.testing import test_ai_native_daemon as fixture_module
TOKEN=fixture_module.TOKEN;M=fixture_module.M;T=fixture_module.T
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon import DaemonError,DaemonHeld
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.telemetry import snapshot
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.readiness import assess
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.canary import run_live_canary
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.canary_cli import main as canary_main
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.operator_cli import main as operator_main
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.service import SupervisedFlightHTTP
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.contracts import FlightBusy
from skeleton.ai.runtime.operational_ai.transport.flight.client import FlightClient,FlightClientError

class NativeDaemonOperatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_module.NativeDaemonAcceptance(methodName='test_empty_queue_is_not_model_failure')
        self.fixture.setUp()
    def tearDown(self):self.fixture.tearDown()
    def test_empty_private_ledger_telemetry_has_null_quantiles(self):
        m=snapshot(self.fixture.ledger)
        self.assertEqual(m['jobs'],0)
        self.assertIsNone(m['inference_ms_p95'])
        self.assertEqual(m['counts']['completed'],0)
    def test_completed_job_exposes_metrics_without_prompt(self):
        f=self.fixture;f.add(prompt='never expose private phrase')
        d=f.daemon();d.start();f.wait_state()
        m=snapshot(f.ledger)
        self.assertEqual(m['counts']['completed'],1)
        self.assertIsInstance(m['queue_wait_ms_p95'],int)
        self.assertIsInstance(m['inference_ms_p95'],int)
        self.assertNotIn('never expose',str(m))
        self.assertNotIn('job1',str(m))
    def test_metrics_hold_on_invalid_observation_bound(self):
        for value in (0,10000,True,'100'):
            with self.subTest(value=value),self.assertRaises(DaemonError):
                snapshot(self.fixture.ledger,maximum=value)
    def test_metrics_bounded_inventory_refuses_truncated_proof(self):
        f=self.fixture
        for n in range(3):f.add(id=f'job{n}',session=f'sess{n}',req=f'req{n}')
        with self.assertRaises(DaemonError):snapshot(f.ledger,maximum=2)
    def test_metrics_does_not_trust_corrupted_timestamps(self):
        f=self.fixture;f.add()
        with f.db.transaction() as conn:
            conn.execute("UPDATE ai_flight_jobs SET created_ns=-1 WHERE job_id='job1'")
        with self.assertRaises(DaemonError):snapshot(f.ledger)
    def test_health_report_is_not_false_model_quality_attestation(self):
        f=self.fixture;d=f.daemon();d.start()
        report=assess(d)
        self.assertTrue(report['serving'])
        self.assertIn('requires-independent-real-model-probe',report['model_generation_quality'])
    def test_paused_operator_mode_reports_unready(self):
        f=self.fixture;d=f.daemon();d.start()
        f.app.operator.pause(approved=True)
        report=assess(d)
        self.assertFalse(report['serving'])
        self.assertEqual(report['reason'],'operator-paused')
    def test_draining_worker_reports_unready(self):
        f=self.fixture;d=f.daemon();d.start();d.stop()
        report=assess(d)
        self.assertFalse(report['serving'])
        self.assertEqual(report['reason'],'manual-drain')
    def test_held_worker_reports_failed_worker_not_green(self):
        f=self.fixture;f.backend.fail=True;f.add()
        d=f.daemon();d.start();f.wait_state(state='held')
        report=assess(d)
        self.assertEqual(report['reason'],'failed-worker')
    def test_fixture_cannot_pass_real_gguf_canary(self):
        f=self.fixture
        with self.assertRaises(DaemonHeld):run_live_canary(f.app)
        self.assertEqual(f.backend.calls,0)
    def test_no_model_or_state_cannot_pass_operator_canary(self):
        f=self.fixture
        stderr=StringIO()
        with redirect_stderr(stderr):
            code=canary_main(['--model-root',str(f.root/'absent'),
                '--fresh-private-state-dir',str(f.state),'--tenant','tenant','--subject','operator'])
        self.assertEqual(code,2)
        self.assertEqual(f.backend.calls,0)
        self.assertNotIn(str(f.state),stderr.getvalue())
    def test_read_only_operator_cli_inspects_authenticated_local_state(self):
        f=self.fixture;f.add()
        stdout=StringIO();stderr=StringIO()
        with redirect_stdout(stdout),redirect_stderr(stderr):
            result=operator_main(['--state-dir',str(f.state),'--tenant','tenant',
             '--subject','operator','--model-sha256',M,'--tokenizer-sha256',T])
        self.assertEqual(result,0,msg=stderr.getvalue())
        doc=json.loads(stdout.getvalue())
        self.assertEqual(doc['telemetry']['counts']['queued'],1)
        self.assertNotIn('Question',stdout.getvalue())
    def test_operator_read_only_cli_rejects_principal_mismatch(self):
        f=self.fixture;f.add()
        stderr=StringIO()
        with redirect_stderr(stderr):
            code=operator_main(['--state-dir',str(f.state),'--tenant','other',
                 '--subject','operator','--model-sha256',M,'--tokenizer-sha256',T])
        self.assertEqual(code,2)
        self.assertNotIn(str(f.state),stderr.getvalue())
    def test_claimed_capacity_error_is_not_blind_retried(self):
        f=self.fixture;f.add()
        with patch.object(f.ledger,'start',side_effect=FlightBusy('model capacity exhausted')):
            d=f.daemon();d.start();f.wait_state(state='held')
            time.sleep(.04)
            self.assertEqual(d.snapshot()['phase'],'held')
            self.assertEqual(f.backend.calls,0)
    def test_paused_mode_serves_503_even_with_healthy_http_socket(self):
        f=self.fixture;f.app.operator.pause(approved=True)
        with SupervisedFlightHTTP(f.app,f.knowledge,TOKEN,port=0,policy=f.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                client=FlightClient(port=server.server_port,token=TOKEN)
                with self.assertRaises(FlightClientError):client.health()
                con=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                con.request('GET','/v2/health',headers={'Host':f'127.0.0.1:{server.server_port}',
                    'Authorization':'Bearer '+TOKEN,'Connection':'close'})
                res=con.getresponse();self.assertEqual(res.status,503)
                raw=json.loads(res.read())
                self.assertEqual(raw['result']['admission']['reason'],'operator-paused')
                con.close()
            finally:server.shutdown();t.join(timeout=5)

    def test_native_protocol_advertises_only_actual_operations_in_daemon_mode(self):
        f=self.fixture
        with SupervisedFlightHTTP(f.app,f.knowledge,TOKEN,port=0,policy=f.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                con=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                con.request('GET','/v2/protocol',headers={'Host':f'127.0.0.1:{server.server_port}',
                    'Authorization':'Bearer '+TOKEN,'Connection':'close'})
                res=con.getresponse();self.assertEqual(res.status,200)
                features=json.loads(res.read())['result']['operations'];con.close()
                self.assertNotIn('work_one',features)
                self.assertIn('submit',features)
                self.assertIn('wait',features)
                self.assertIn('cancel',features)
            finally:server.shutdown();t.join(timeout=5)

    def test_failed_worker_rejects_new_http_submission_before_queue_write(self):
        f=self.fixture;f.spine.create('sess1');f.backend.fail=True
        with SupervisedFlightHTTP(f.app,f.knowledge,TOKEN,port=0,policy=f.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                client=FlightClient(port=server.server_port,token=TOKEN,timeout=3)
                client.request('submit',{'job_id':'job1','session_id':'sess1','request_id':'req1','question':'first'})
                f.wait_state(state='held')
                self.assertEqual(daemon.snapshot()['phase'],'held')
                with self.assertRaises(FlightClientError):
                    client.request('submit',{'job_id':'job2','session_id':'sess1','request_id':'req2','question':'second'})
                self.assertEqual(f.ledger.state_count()['held'],1)
                self.assertEqual(f.backend.calls,1)
            finally:server.shutdown();t.join(timeout=5)

    def test_draining_worker_rejects_new_submission(self):
        f=self.fixture;f.spine.create('sess1')
        with SupervisedFlightHTTP(f.app,f.knowledge,TOKEN,port=0,policy=f.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                daemon.stop(timeout_ms=500)
                client=FlightClient(port=server.server_port,token=TOKEN,timeout=3)
                with self.assertRaises(FlightClientError):
                    client.request('submit',{'job_id':'job2','session_id':'sess1','request_id':'req2','question':'after stop'})
                self.assertEqual(f.backend.calls,0)
            finally:server.shutdown();t.join(timeout=5)

    def test_native_supervisor_does_not_accept_work_during_stall(self):
        f=self.fixture;f.backend.block=True;f.add()
        daemon=f.daemon();daemon.start()
        self.assertTrue(f.backend.entered.wait(2))
        time.sleep(1.1)
        self.assertFalse(daemon.accepting())
        f.backend.release.set();f.wait_state()
        self.assertTrue(daemon.accepting())

    def test_tail_latency_uses_nearest_rank_not_lower_minimum(self):
        from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.telemetry import _percentile
        self.assertEqual(_percentile([3,100],95),100)
        self.assertEqual(_percentile([3,100],50),3)
        self.assertEqual(_percentile([3],95),3)

if __name__=='__main__':unittest.main()
