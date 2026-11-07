"""Integration and adversarial acceptance of automatic local native inference.

Every test uses original deterministic fixture generation; this test cannot
qualify a real GGUF, target hardware, licensing or external connectivity.
"""
from __future__ import annotations
from hashlib import sha256
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import (
    Identity,SpineDatabase,ExecutionSpine,SpineLimits)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.flight_control import FlightLedger,NativeFlightWorker
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.operator import FlightOperator
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.production import FlightApplication
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.contracts import FlightSpec
from skeleton.ai.runtime.operational_ai.orchestration.flight_control import controls
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.clock import ClockStamp
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon import (
    InferenceDaemon,DaemonPolicy,DaemonBusy,DaemonError,DaemonHeld,SupervisedFlightHTTP)
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.preflight import inspect as preflight
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.status import DaemonStatus
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.protocol import capabilities
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.acceptance import require_live_probe
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.context.knowledge_plane import KnowledgePlane
from skeleton.ai.runtime.operational_ai.transport.flight.client import FlightClient,FlightClientError
from skeleton.ai.runtime.operational_ai.transport.flight.dispatch import FlightDispatcher
from skeleton.ai.runtime.operational_ai.transport.flight.http import FlightHTTPServer
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
from skeleton.ai.runtime.operational_ai.deployment.boot.identity import PrincipalBinding,establish_binding

M='c'*64
T='d'*64
TOKEN='Q'*48

class LocalBackend:
    model_digest=M;tokenizer_digest=T
    def __init__(self):
        self.calls=0;self.fail=False;self.entered=threading.Event()
        self.release=threading.Event();self.block=False
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1;self.entered.set()
        if self.block and not self.release.wait(10):
            raise RuntimeError('fixture generation intentionally blocked')
        if self.fail:raise RuntimeError('private-key-NEVER-LEAK')
        result='Local native fixture answer '+str(self.calls)
        return Generated(result,48,10,sha256(result.encode()).hexdigest(),M,T,'stop')

class NativeDaemonAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='skeleton-ai-daemon-', dir=Path.home())
        self.root=Path(self.temp.name)
        self.state=self.root/'private';self.state.mkdir(mode=0o700)
        establish_binding(self.state,PrincipalBinding('tenant','operator',M,T))
        self.locks=self.state/'gates';self.locks.mkdir(mode=0o700)
        self.db=SpineDatabase(self.state)
        self.gate=SessionGate(self.locks)
        self.identity=Identity('tenant','operator',M,T)
        self.backend=LocalBackend()
        self.knowledge=KnowledgePlane(self.db,self.identity)
        self.spine=ExecutionSpine(db=self.db,session_gate=self.gate,backend=self.backend,
            identity=self.identity,limits=SpineLimits(context_tokens=8192,max_output_tokens=64,deadline_ms=10000),
            evidence_provider=self.knowledge.evidence_provider())
        self.ledger=FlightLedger(self.db,self.identity)
        self.worker=NativeFlightWorker(self.ledger,self.spine,'daemon_worker_01')
        self.app=FlightApplication(self.spine,self.ledger,self.worker,FlightOperator(self.ledger,self.spine))
        self.policy=DaemonPolicy(poll_ms=20,shutdown_grace_ms=500,health_stall_ms=1000)
        self.daemons=[]
    def tearDown(self):
        self.backend.release.set()
        for daemon in self.daemons:
            daemon.stop(timeout_ms=2000)
        self.gate.close();self.db.close();self.temp.cleanup()

    def daemon(self):
        d=InferenceDaemon(self.app,policy=self.policy);self.daemons.append(d)
        return d

    def add(self,id='job1',session='session1',req='req1',prompt='Question'):
        self.spine.create(session)
        return self.ledger.submit(FlightSpec(self.identity,id,session,req,prompt))

    def wait_state(self,id='job1',state='completed',limit=3):
        end=time.monotonic()+limit
        while time.monotonic()<end:
            record=self.ledger.inspect(id)
            if record['state']==state:return record
            time.sleep(.015)
        self.fail('queued task never entered expected '+state)

    def test_auto_worker_drains_queued_inference_without_http_work_one(self):
        self.add();daemon=self.daemon();daemon.start()
        job=self.wait_state()
        self.assertEqual(job['result']['revision'],1)
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(len(self.spine.history('session1')),2)
        self.assertEqual(daemon.snapshot()['completed_jobs'],1)

    def test_auto_worker_wakes_after_submission_without_manual_polling(self):
        daemon=self.daemon();daemon.start()
        self.add();daemon.notify();self.wait_state()
        self.assertEqual(self.backend.calls,1)

    def test_daemon_start_once_and_second_start_fails_closed(self):
        daemon=self.daemon();daemon.start()
        with self.assertRaises(DaemonError):daemon.start()

    def test_daemon_cannot_be_started_after_stopping(self):
        daemon=self.daemon();daemon.start();daemon.stop()
        with self.assertRaises(DaemonError):daemon.start()

    def test_unsupported_policy_values_rejected(self):
        for kwargs in ({'poll_ms':0},{'poll_ms':1_000_000},
                       {'startup_max_jobs':50000},{'shutdown_grace_ms':0},
                       {'health_stall_ms':True}):
            with self.subTest(kwargs=kwargs),self.assertRaises(DaemonError):
                DaemonPolicy(**kwargs)

    def test_existing_stale_started_work_blocks_daemon_activation(self):
        self.add();ticket=self.ledger.claim('stranded_worker')
        self.ledger.start(ticket)
        prior=self.ledger.clock
        class NewBoot:
            def stamp(self):
                s=prior.stamp()
                return ClockStamp('99999999-9999-9999-9999-999999999999',s.tick,s.wall)
        self.ledger.clock=NewBoot()
        daemon=self.daemon()
        with self.assertRaises(DaemonHeld):daemon.start()
        self.assertEqual(self.backend.calls,0)

    def test_stale_claimed_without_model_start_also_requires_review(self):
        self.add();self.ledger.claim('stranded_worker')
        old=self.ledger.clock
        class NewBoot:
            def stamp(self):
                s=old.stamp()
                return ClockStamp('99999999-9999-9999-9999-999999999999',s.tick,s.wall)
        self.ledger.clock=NewBoot()
        with self.assertRaises(DaemonHeld):self.daemon().start()

    def test_paused_queue_never_generates_until_operator_approved_resume(self):
        self.add();self.app.operator.pause(approved=True)
        daemon=self.daemon();daemon.start()
        time.sleep(.12)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(self.ledger.inspect('job1')['state'],'queued')
        self.app.operator.resume(approved=True)
        daemon.notify();self.wait_state()
        self.assertEqual(self.backend.calls,1)

    def test_failed_model_holds_job_and_worker_without_retry(self):
        self.backend.fail=True;self.add()
        daemon=self.daemon();daemon.start()
        self.wait_state(state='held')
        time.sleep(.08)
        self.assertEqual(self.backend.calls,1)
        status=daemon.snapshot()
        self.assertEqual(status['phase'],'held')
        self.assertEqual(status['last_error_type'],'RuntimeError')
        self.assertNotIn('private-key',str(status))

    def test_held_daemon_never_auto_restarts_after_failure(self):
        self.backend.fail=True;self.add()
        daemon=self.daemon();daemon.start()
        self.wait_state(state='held')
        self.backend.fail=False
        time.sleep(.1)
        self.assertEqual(self.backend.calls,1)

    def test_noninterruptible_model_must_finish_before_cleanup(self):
        self.backend.block=True;self.add()
        daemon=self.daemon();daemon.start()
        self.assertTrue(self.backend.entered.wait(2))
        with self.assertRaises(DaemonBusy):daemon.stop(timeout_ms=15)
        self.assertEqual(daemon.snapshot()['phase'],'draining')
        self.backend.release.set()
        daemon.stop(timeout_ms=1500)
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(self.ledger.inspect('job1')['state'],'completed')

    def test_queued_cancel_does_not_execute_model(self):
        self.add();self.ledger.cancel('job1')
        daemon=self.daemon();daemon.start();time.sleep(.1)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(self.ledger.inspect('job1')['state'],'cancelled')

    def test_read_only_startup_proof(self):
        proof=preflight(self.app,self.policy)
        self.assertEqual(proof['reviewed_jobs'],0)
        self.assertEqual(proof['verified_events'],0)
        self.assertEqual(proof['state'],'running')
        self.assertEqual(self.backend.calls,0)

    def test_integrity_corruption_blocks_startup(self):
        self.add()
        with self.db.transaction() as conn:
            conn.execute("UPDATE ai_flight_jobs SET state='cancelled' WHERE job_id='job1'")
        with self.assertRaises(Exception):self.daemon().start()
        self.assertEqual(self.backend.calls,0)

    def test_model_identity_mismatch_blocks_startup(self):
        self.backend.model_digest='0'*64
        with self.assertRaises(DaemonHeld):self.daemon().start()
        self.assertEqual(self.backend.calls,0)

    def test_empty_queue_is_not_model_failure(self):
        daemon=self.daemon();daemon.start();time.sleep(.12)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(daemon.snapshot()['failures'],0)
        self.assertGreater(daemon.snapshot()['idle_polls'],0)

    def test_stop_without_start_does_not_spawn_worker(self):
        daemon=self.daemon();result=daemon.stop()
        self.assertEqual(result['phase'],'stopped')
        self.assertFalse(daemon.notify())

    def test_status_snapshot_contains_no_prompt_and_bounded_error_type(self):
        self.add(prompt='VERY_SECRET_STRING_IS_HERE')
        daemon=self.daemon();daemon.start();self.wait_state()
        snapshot=daemon.snapshot()
        self.assertNotIn('VERY_SECRET',str(snapshot))
        self.assertNotIn('job1',str(snapshot))
        self.assertEqual(snapshot['readiness'],'scheduler-only-not-model-quality')

    def test_daemon_protocol_denies_remote_fallback_and_model_promotion(self):
        caps=capabilities()
        self.assertEqual(caps['concurrent_model_calls'],1)
        self.assertEqual(caps['lease_recovery'],'operator-only')
        self.assertEqual(caps['native_model_fallback'],'refused')

    def test_model_qualification_requires_real_probe_not_fixture(self):
        with self.assertRaises(DaemonHeld):require_live_probe({'status':'verified-native-generation','model_calls':1,'generated_tokens':5,'fixture':True,'model_sha256':M})
        with self.assertRaises(DaemonHeld):require_live_probe({'status':'fixture','model_calls':1,'generated_tokens':5,'fixture':False,'model_sha256':M})

    def test_health_observes_stall_without_killing_native_computation(self):
        self.backend.block=True;self.add()
        daemon=self.daemon();daemon.start()
        self.assertTrue(self.backend.entered.wait(2))
        time.sleep(1.1)
        self.assertTrue(daemon.snapshot()['stall_observed'])
        self.backend.release.set();self.wait_state()
        self.assertEqual(self.backend.calls,1)

    def test_bounded_wait_rejects_large_poll_duration(self):
        dispatcher=FlightDispatcher(self.app)
        self.add()
        with self.assertRaises(ContractViolation):
            dispatcher.dispatch('wait',{'job_id':'job1','max_wait_ms':100000})

    def test_manual_work_route_can_be_disabled_even_for_authenticated_client(self):
        dispatcher=FlightDispatcher(self.app,allow_manual_work=False)
        self.add()
        with self.assertRaises(ContractViolation):dispatcher.dispatch('work_one',{})
        self.assertEqual(self.backend.calls,0)

    def test_async_wait_returns_completed_receipt(self):
        self.add();daemon=self.daemon();daemon.start()
        dispatcher=FlightDispatcher(self.app,allow_manual_work=False)
        job=dispatcher.dispatch('wait',{'job_id':'job1','max_wait_ms':1500})['job']
        self.assertEqual(job['state'],'completed')
        self.assertEqual(self.backend.calls,1)

    def test_duplicate_submit_does_not_double_compute(self):
        self.add();daemon=self.daemon();daemon.start();self.wait_state()
        accepted=self.ledger.submit(FlightSpec(self.identity,'job1','session1','req1','Question'))
        self.assertTrue(accepted['replayed'])
        self.assertEqual(self.backend.calls,1)

    def test_repeated_job_status_is_read_only(self):
        self.add();dispatcher=FlightDispatcher(self.app,allow_manual_work=False)
        for _ in range(6):
            self.assertEqual(dispatcher.dispatch('job',{'job_id':'job1'})['job']['state'],'queued')
        self.assertEqual(self.backend.calls,0)

    def test_dispatcher_does_not_erase_committed_submission_on_notification_error(self):
        self.spine.create('sessX')
        def broken():raise ValueError('event notification unavailable')
        dispatcher=FlightDispatcher(self.app,on_submit=broken)
        r=dispatcher.dispatch('submit',{'job_id':'jobX','session_id':'sessX','request_id':'reqX','question':'Need response'})
        self.assertFalse(r['job']['replayed'])
        self.assertEqual(self.ledger.inspect('jobX')['state'],'queued')

    def test_run_inference_with_native_http_and_auto_background_worker(self):
        self.spine.create('session1')
        with SupervisedFlightHTTP(self.app,self.knowledge,TOKEN,port=0,policy=self.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                client=FlightClient(port=server.server_port,token=TOKEN,timeout=4)
                self.assertEqual(client.health()['supervisor']['phase'],'running')
                accepted=client.request('submit',{'job_id':'job1','session_id':'session1',
                      'request_id':'req1','question':'automatic native model inference'})
                self.assertEqual(accepted['job']['state'],'queued')
                with self.assertRaises(FlightClientError):client.request('work_one',{})
                result=client.wait('job1',max_wait_ms=1400)
                self.assertEqual(result['job']['state'],'completed')
                self.assertEqual(self.backend.calls,1)
            finally:server.shutdown();t.join(timeout=5)

    def test_health_route_requires_same_bearer_as_inference(self):
        with SupervisedFlightHTTP(self.app,self.knowledge,TOKEN,port=0,policy=self.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                conn.request('GET','/v2/health',headers={'Host':f'127.0.0.1:{server.server_port}','Authorization':'Bearer BAD','Connection':'close'})
                resp=conn.getresponse()
                self.assertEqual(resp.status,401)
                resp.read();conn.close()
            finally:server.shutdown();t.join(timeout=5)

    def test_client_cancel_only_own_queued_inference(self):
        self.spine.create('session1')
        with SupervisedFlightHTTP(self.app,self.knowledge,TOKEN,port=0,policy=self.policy) as (server,daemon):
            # Hold worker by operator mode before client submits. Daemon does not
            # promote queued work until independent operator resumes.
            self.app.operator.pause(approved=True)
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                client=FlightClient(port=server.server_port,token=TOKEN,timeout=4)
                client.request('submit',{'job_id':'job1','session_id':'session1','request_id':'req1','question':'cancel me'})
                receipt=client.cancel('job1')['job']
                self.assertEqual(receipt['state'],'cancelled')
                self.assertEqual(self.backend.calls,0)
            finally:server.shutdown();t.join(timeout=5)

    def test_health_rejects_unauthenticated_browser_origin(self):
        with SupervisedFlightHTTP(self.app,self.knowledge,TOKEN,port=0,policy=self.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                conn.request('GET','/v2/health',headers={'Host':f'127.0.0.1:{server.server_port}','Authorization':'Bearer '+TOKEN,'Origin':'https://attacker.test','Connection':'close'})
                resp=conn.getresponse();self.assertEqual(resp.status,403);resp.read();conn.close()
            finally:server.shutdown();t.join(timeout=5)

    def test_many_sessions_are_processed_by_one_native_backend_without_overlap(self):
        for index in range(16):
            self.add(id=f'job{index}',session=f'sess{index}',req=f'req{index}',prompt=f'question {index}')
        daemon=self.daemon();daemon.start()
        end=time.monotonic()+8
        while time.monotonic()<end:
            if daemon.snapshot()['completed_jobs']==16:break
            time.sleep(.015)
        self.assertEqual(daemon.snapshot()['completed_jobs'],16)
        self.assertEqual(self.backend.calls,16)
        for index in range(16):
            self.assertEqual(self.ledger.inspect(f'job{index}')['state'],'completed')

    def test_stop_then_new_supervisor_does_not_recompute_completed_receipt(self):
        self.add()
        first=self.daemon();first.start();self.wait_state();first.stop()
        replacement=self.daemon();replacement.start()
        time.sleep(.08)
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(self.ledger.inspect('job1')['state'],'completed')

    def test_client_replayed_job_after_complete_does_not_double_generate(self):
        self.spine.create('session1')
        with SupervisedFlightHTTP(self.app,self.knowledge,TOKEN,port=0,policy=self.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                client=FlightClient(port=server.server_port,token=TOKEN)
                job={'job_id':'job1','session_id':'session1','request_id':'req1','question':'same task'}
                client.request('submit',job)
                self.assertEqual(client.wait('job1',max_wait_ms=1500)['job']['state'],'completed')
                replay=client.request('submit',job)
                self.assertTrue(replay['job']['replayed'])
                self.assertEqual(self.backend.calls,1)
            finally:server.shutdown();t.join(timeout=5)

    def test_running_cancellation_is_observed_but_native_kernel_is_not_killed(self):
        self.backend.block=True;self.add()
        daemon=self.daemon();daemon.start()
        self.assertTrue(self.backend.entered.wait(2))
        record=self.ledger.cancel('job1')
        self.assertEqual(record['state'],'running')
        self.assertEqual(record['cancel_requested'],1)
        self.backend.release.set()
        self.wait_state()
        self.assertEqual(self.backend.calls,1)

    def test_client_http_long_poll_caps_to_two_seconds(self):
        self.spine.create('session1')
        self.app.operator.pause(approved=True)
        with SupervisedFlightHTTP(self.app,self.knowledge,TOKEN,port=0,policy=self.policy) as (server,daemon):
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                client=FlightClient(port=server.server_port,token=TOKEN,timeout=4)
                client.request('submit',{'job_id':'job1','session_id':'session1',
                                         'request_id':'req1','question':'pending'})
                start=time.monotonic()
                report=client.wait('job1',max_wait_ms=100)
                self.assertLess(time.monotonic()-start,1.0)
                self.assertEqual(report['job']['state'],'queued')
                self.assertEqual(self.backend.calls,0)
            finally:server.shutdown();t.join(timeout=5)

if __name__=='__main__':unittest.main()
