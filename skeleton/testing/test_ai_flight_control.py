"""Adversarial durable flight-control acceptance; no live model qualification.

Fixtures intentionally inject deterministic responses; tests assert custody,
not language quality or native model activation.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from hashlib import sha256
import json,os,sqlite3,tempfile,time,threading,unittest

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import (
    Identity,SpineDatabase,ExecutionSpine,SpineLimits)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    SpineError,Busy,Conflict)
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.orchestration.flight_control import (
    FlightSpec,FlightPolicy,FlightLedger,FlightError,FlightConflict,FlightBusy,
    NativeFlightWorker,expired,reconcile,inspect)
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.clock import (
    BootClock,ClockStamp)

M='a'*64
T='b'*64

class FakeBackend:
    model_digest=M; tokenizer_digest=T
    def __init__(self):self.calls=0;self.exc=None
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1
        if self.exc is not None:raise self.exc
        value=f'verified fixture response {self.calls}'
        return Generated(value,32,5,sha256(value.encode()).hexdigest(),M,T,'stop')

class MutableClock:
    def __init__(self):
        self.boot='1'*8+'-'+'1'*4+'-'+'1'*4+'-'+'1'*4+'-'+'1'*12
        self.tick=1_000_000_000
        self.wall=1_700_000_000_000_000_000
    def stamp(self):return ClockStamp(self.boot,self.tick,self.wall)
    def travel(self,ms):self.tick+=ms*1_000_000;self.wall+=ms*1_000_000
    def reboot(self):self.boot='2'*8+'-'+'2'*4+'-'+'2'*4+'-'+'2'*4+'-'+'2'*12;self.tick=10

class Flights(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='flight-')
        self.root=Path(self.temp.name)/'private';self.root.mkdir(mode=0o700)
        self.lock=self.root/'locks';self.lock.mkdir(mode=0o700)
        self.identity=Identity('tenant1','human1',M,T)
        self.backend=FakeBackend()
        self.db=SpineDatabase(self.root)
        self.gate=SessionGate(self.lock)
        self.limits=SpineLimits(context_tokens=8192,max_output_tokens=64,deadline_ms=4000)
        self.spine=ExecutionSpine(db=self.db,session_gate=self.gate,backend=self.backend,
                                  identity=self.identity,limits=self.limits)
        self.spine.create('chat1')
        self.clock=BootClock()
        self.ledger=FlightLedger(self.db,self.identity,clock=self.clock,
                                settings=FlightPolicy(lease_ms=2000,max_running=4,max_claimed=8))

    def tearDown(self):
        self.gate.close();self.db.close();self.temp.cleanup()

    def spec(self,n=1,**args):
        return FlightSpec(self.identity,f'job{n}','chat1',f'ask{n}',f'Explain idea {n}',**args)

    def submit(self,n=1,**kwargs):return self.ledger.submit(self.spec(n,**kwargs))

    def test_default_policy_and_identity(self):
        self.assertEqual(self.ledger.state_count()['queued'],0)
        self.assertEqual(self.ledger.identity.key(),self.identity.key())
        self.assertEqual(self.ledger.settings.max_running,4)

    def test_duplicate_submit_is_exact_idempotent(self):
        first=self.submit()
        second=self.submit()
        self.assertFalse(first['replayed']);self.assertTrue(second['replayed'])
        self.assertEqual(self.ledger.state_count()['queued'],1)
        self.assertEqual(inspect(self.ledger)['events'],1)

    def test_duplicate_job_altered_prompt_rejected(self):
        self.submit()
        with self.assertRaises(FlightConflict):self.ledger.submit(
            FlightSpec(self.identity,'job1','chat1','ask1','malicious replacement'))

    def test_duplicate_request_other_job_id_rejected(self):
        self.submit()
        with self.assertRaises(FlightConflict):self.ledger.submit(
            FlightSpec(self.identity,'job7','chat1','ask1','Explain idea 1'))

    def test_priority_scheduling(self):
        self.submit(1,priority=1);self.submit(2,priority=8)
        self.assertEqual(self.ledger.claim('worker1').job_id,'job2')

    def test_full_native_path_and_replay(self):
        self.submit()
        outcome=NativeFlightWorker(self.ledger,self.spine,'w1').run_one()
        self.assertEqual(outcome.state,'completed')
        self.assertEqual(outcome.revision,1)
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(self.ledger.inspect('job1')['result']['model_sha256'],M)
        self.assertIsNone(NativeFlightWorker(self.ledger,self.spine,'w1').run_one())
        self.assertEqual(inspect(self.ledger)['states']['completed'],1)

    def test_multiple_queued_requests_run_in_order(self):
        for n in range(1,5):self.submit(n)
        results=NativeFlightWorker(self.ledger,self.spine,'w1').drain(maximum=4)
        self.assertEqual([x.revision for x in results],[1,2,3,4])
        self.assertEqual(self.backend.calls,4)

    def test_drain_requires_finite_budget(self):
        with self.assertRaises(FlightConflict):NativeFlightWorker(self.ledger,self.spine,'w1').drain(maximum=0)
        with self.assertRaises(FlightConflict):NativeFlightWorker(self.ledger,self.spine,'w1').drain(maximum=257)

    def test_no_model_when_queue_empty(self):
        self.assertIsNone(NativeFlightWorker(self.ledger,self.spine,'w1').run_one())
        self.assertEqual(self.backend.calls,0)

    def test_claim_lease_cannot_start_after_expiry(self):
        self.ledger.clock=MutableClock();self.submit()
        ticket=self.ledger.claim('w1')
        self.ledger.clock.travel(2100)
        with self.assertRaises(FlightConflict):self.ledger.start(ticket)
        self.assertEqual(self.backend.calls,0)

    def test_claim_cannot_start_across_boot(self):
        self.ledger.clock=MutableClock();self.submit()
        ticket=self.ledger.claim('w1')
        self.ledger.clock.reboot()
        with self.assertRaises(FlightConflict):self.ledger.start(ticket)

    def test_stale_ticket_after_heartbeat_cannot_start(self):
        self.submit();ticket=self.ledger.claim('w1')
        updated=self.ledger.heartbeat(ticket)
        with self.assertRaises(FlightConflict):self.ledger.start(ticket)
        self.ledger.start(updated)

    def test_cancel_queued_never_runs(self):
        self.submit();self.ledger.cancel('job1')
        self.assertEqual(self.ledger.inspect('job1')['state'],'cancelled')
        self.assertIsNone(self.ledger.claim('w1'))
        self.assertEqual(self.backend.calls,0)

    def test_cancel_claimed_prevents_start(self):
        self.submit();ticket=self.ledger.claim('w1')
        self.ledger.cancel('job1')
        with self.assertRaises(FlightConflict):self.ledger.start(ticket)

    def test_cancel_running_marks_request_not_forged_completion(self):
        self.submit();ticket=self.ledger.claim('w1');self.ledger.start(ticket)
        report=self.ledger.cancel('job1')
        self.assertEqual(report['state'],'running')
        self.assertEqual(report['cancel_requested'],1)

    def test_worker_backend_error_holds_job(self):
        self.submit();self.backend.exc=RuntimeError('fixture-fault')
        with self.assertRaises(RuntimeError):NativeFlightWorker(self.ledger,self.spine,'w1').run_one()
        self.assertEqual(self.ledger.inspect('job1')['state'],'held')
        self.assertEqual(self.ledger.inspect('job1')['hold_reason'],'RuntimeError')
        self.assertIsNone(self.ledger.claim('w1'))
        self.assertEqual(self.backend.calls,1)

    def test_unauthorized_identity_cannot_read_job(self):
        self.submit()
        alien=Identity('other','human1',M,T)
        wrong=FlightLedger(self.db,alien)
        with self.assertRaises(FlightConflict):wrong.inspect('job1')
        with self.assertRaises(FlightConflict):wrong.request_for('job1')
        self.assertIsNone(wrong.claim('w1'))

    def test_unauthorized_identity_cannot_submit(self):
        with self.assertRaises(FlightConflict):self.ledger.submit(
            FlightSpec(Identity('other','human1',M,T),'job1','chat1','ask1','content'))

    def test_invalid_priority_fails_before_write(self):
        for priority in (-1,10,1.5,True):
            with self.subTest(priority=priority),self.assertRaises(FlightError):self.spec(priority=priority)

    def test_invalid_worker_identifier(self):
        self.submit()
        with self.assertRaises(SpineError):self.ledger.claim('../w')
        with self.assertRaises(SpineError):NativeFlightWorker(self.ledger,self.spine,'bad/worker')

    def test_queue_per_principal_cap(self):
        self.ledger.settings=FlightPolicy(max_queued=2,max_per_principal=2,max_running=1,max_claimed=2)
        self.submit(1);self.submit(2)
        with self.assertRaises(FlightBusy):self.submit(3)

    def test_queue_releases_capacity_on_completion(self):
        self.ledger.settings=FlightPolicy(max_queued=1,max_per_principal=1,max_running=1,max_claimed=1)
        self.submit(1)
        NativeFlightWorker(self.ledger,self.spine,'w1').run_one()
        self.submit(2)
        self.assertEqual(self.ledger.state_count()['queued'],1)

    def test_worker_identity_mismatch(self):
        self.submit()
        stranger=Identity('other','human',M,T)
        with self.assertRaises(FlightConflict):NativeFlightWorker(FlightLedger(self.db,stranger),self.spine,'w1')

    def test_worker_does_not_repeat_spine_committed_request(self):
        self.submit()
        self.spine.turn('chat1','ask1','Explain idea 1')
        self.assertEqual(self.backend.calls,1)
        outcome=NativeFlightWorker(self.ledger,self.spine,'w1').run_one()
        self.assertTrue(outcome.recovered)
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(outcome.state,'completed')

    def test_claimed_expired_explicit_requeue_without_model(self):
        self.ledger.clock=MutableClock();self.submit()
        old=self.ledger.claim('w1')
        self.ledger.clock.travel(2100)
        with self.assertRaises(FlightConflict):reconcile(self.ledger,self.spine,approved=False)
        summary=reconcile(self.ledger,self.spine,approved=True)
        self.assertEqual(summary['requeued_unstarted'],1)
        self.assertEqual(summary['model_calls'],0)
        new=self.ledger.claim('w1')
        self.assertGreater(new.fence,old.fence)
        with self.assertRaises(FlightConflict):self.ledger.start(old)

    def test_running_expired_without_spine_receipt_held(self):
        self.ledger.clock=MutableClock();self.submit()
        t=self.ledger.claim('w1');self.ledger.start(t)
        self.ledger.clock.travel(2100)
        result=reconcile(self.ledger,self.spine,approved=True)
        self.assertEqual(result['held_uncertain'],1)
        self.assertEqual(self.ledger.inspect('job1')['state'],'held')
        self.assertEqual(self.backend.calls,0)

    def test_running_expired_with_spine_receipt_recovered(self):
        self.ledger.clock=MutableClock();self.submit()
        t=self.ledger.claim('w1');self.ledger.start(t)
        self.spine.turn('chat1','ask1','Explain idea 1')
        self.ledger.clock.travel(2100)
        result=reconcile(self.ledger,self.spine,approved=True)
        self.assertEqual(result['recovered_from_committed_receipt'],1)
        self.assertEqual(self.ledger.inspect('job1')['state'],'completed')
        self.assertEqual(self.backend.calls,1)

    def test_recovery_does_not_mutate_live_claims(self):
        self.submit();self.ledger.claim('w1')
        result=reconcile(self.ledger,self.spine,approved=True)
        self.assertEqual(result['live'],1)
        self.assertEqual(self.ledger.inspect('job1')['state'],'claimed')

    def test_job_chain_tamper_detected(self):
        self.submit()
        self.db._db.execute("UPDATE ai_flight_events SET event_digest=? WHERE job_id='job1'",('e'*64,))
        with self.assertRaises(FlightConflict):inspect(self.ledger)
        with self.assertRaises(FlightConflict):self.submit()

    def test_result_tamper_detected(self):
        self.submit();NativeFlightWorker(self.ledger,self.spine,'w1').run_one()
        self.db._db.execute("UPDATE ai_flight_jobs SET receipt_json=? WHERE job_id='job1'",(b'{}',))
        with self.assertRaises(FlightConflict):self.ledger.inspect('job1')
        with self.assertRaises(FlightConflict):inspect(self.ledger)

    def test_private_job_prompt_not_leaked_through_events(self):
        self.ledger.submit(FlightSpec(self.identity,'job1','chat1','ask1','private-secret:abc'))
        with self.db.snapshot() as conn:
            raw=b''.join(row[0] for row in conn.execute('SELECT event_json FROM ai_flight_events'))
        self.assertNotIn(b'private-secret',raw)

    def test_closing_session_does_not_forge_inference(self):
        self.submit()
        self.spine.close('chat1')
        with self.assertRaises(Conflict):NativeFlightWorker(self.ledger,self.spine,'w1').run_one()
        self.assertEqual(self.ledger.inspect('job1')['state'],'held')
        self.assertEqual(self.backend.calls,0)

    def test_introspection_is_bounded(self):
        for n in range(1,4):self.submit(n)
        with self.assertRaises(FlightConflict):inspect(self.ledger,max_jobs=0)
        with self.assertRaises(FlightConflict):inspect(self.ledger,max_jobs=2)
        with self.assertRaises(FlightBusy):self.ledger.pending(limit=2)

    def test_boot_id_readable(self):
        stamp=BootClock().stamp()
        self.assertEqual(len(stamp.boot),36)
        self.assertGreater(stamp.tick,0)
        self.assertGreater(stamp.wall,0)

    def test_schema_version_mismatch_fails_closed(self):
        self.db._db.execute("UPDATE controls SET value='999' WHERE control='flight_schema'")
        with self.assertRaises(FlightConflict):FlightLedger(self.db,self.identity)

    def test_no_automatic_inference_reclaim_after_expired_spine_pending(self):
        from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import requests
        req=self.spec().request()
        with self.db.transaction() as conn:requests.reserve(conn,req,self.limits,lease_ns=1)
        time.sleep(.002)
        with self.db.transaction() as conn:
            with self.assertRaises(Busy):requests.reserve(conn,req,self.limits)
        self.assertEqual(self.backend.calls,0)

if __name__=='__main__':unittest.main()

from skeleton.ai.runtime.operational_ai.orchestration.flight_control import (
    configure,report,export,submit_many,FlightOperator)

class FlightOperatorTests(Flights):
    def test_pause_requires_operator_approval(self):
        self.submit()
        with self.assertRaises(FlightConflict):configure(self.ledger,'paused')
        self.assertEqual(configure(self.ledger,'paused',approved=True)['after'],'paused')
        with self.assertRaises(FlightBusy):self.ledger.claim('w1')
        self.assertEqual(self.backend.calls,0)
        self.assertTrue(configure(self.ledger,'running',approved=True)['changed'])
        self.assertIsNotNone(self.ledger.claim('w1'))

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(FlightConflict):configure(self.ledger,'unsafe',approved=True)
        self.db._db.execute("INSERT INTO controls(control,value) VALUES ('flight_mode','broken')")
        with self.assertRaises(FlightConflict):self.ledger.claim('w1')
        with self.assertRaises(FlightConflict):inspect(self.ledger)

    def test_repeated_pause_is_idempotent(self):
        first=configure(self.ledger,'paused',approved=True)
        second=configure(self.ledger,'paused',approved=True)
        self.assertTrue(first['changed']);self.assertFalse(second['changed'])

    def test_lease_monitor_is_read_only(self):
        self.ledger.clock=MutableClock();self.submit()
        self.ledger.claim('w1');self.ledger.clock.travel(2100)
        before=self.db._db.total_changes
        output=report(self.ledger)
        self.assertEqual(output['stale_count'],1)
        self.assertEqual(output['actions_taken'],0)
        self.assertEqual(self.db._db.total_changes,before)

    def test_monitor_honors_boot_replacement(self):
        self.ledger.clock=MutableClock();self.submit()
        self.ledger.claim('w1');self.ledger.clock.reboot()
        self.assertTrue(report(self.ledger)['stale'][0]['boot_mismatch'])

    def test_proof_excludes_private_prompt_bytes(self):
        self.ledger.submit(FlightSpec(self.identity,'job1','chat1','ask1','operator-private-token'))
        result=export(self.ledger)
        self.assertNotIn('operator-private-token',json.dumps(result))
        self.assertEqual(len(result['manifest_sha256']),64)

    def test_batch_submission_all_or_none_on_conflict(self):
        one=self.spec(1)
        invalid=FlightSpec(self.identity,'job2','chat1','ask1','other prompt')
        with self.assertRaises(FlightConflict):submit_many(self.ledger,[one,invalid])
        self.assertEqual(self.ledger.state_count()['queued'],0)

    def test_batch_submission_all_or_none_on_capacity(self):
        self.ledger.settings=FlightPolicy(max_queued=2,max_per_principal=2,max_running=1,max_claimed=2)
        with self.assertRaises(FlightBusy):submit_many(self.ledger,[self.spec(1),self.spec(2),self.spec(3)])
        self.assertEqual(self.ledger.state_count()['queued'],0)

    def test_batch_submission_commits_every_entry(self):
        results=submit_many(self.ledger,[self.spec(1),self.spec(2),self.spec(3)])
        self.assertEqual(len(results),3)
        self.assertEqual(self.ledger.state_count()['queued'],3)
        replay=submit_many(self.ledger,[self.spec(1),self.spec(2),self.spec(3)])
        self.assertTrue(all(x['replayed'] for x in replay))

    def test_batch_duplicate_job_and_request_rejected_before_write(self):
        with self.assertRaises(FlightConflict):submit_many(self.ledger,[self.spec(),self.spec()])
        with self.assertRaises(FlightConflict):submit_many(self.ledger,[self.spec(),FlightSpec(self.identity,'new','chat1','ask1','x')])
        self.assertEqual(self.ledger.state_count()['queued'],0)

    def test_batch_rejects_generator_above_hard_cap(self):
        specs=(self.spec(n) for n in range(1,200))
        with self.assertRaises(FlightConflict):submit_many(self.ledger,specs,maximum=16)
        self.assertEqual(self.ledger.state_count()['queued'],0)

    def test_per_session_active_serialization(self):
        self.submit(1);self.submit(2)
        first=self.ledger.claim('w1')
        self.assertIsNone(self.ledger.claim('w2'))
        self.ledger.start(first)
        self.assertIsNone(self.ledger.claim('w2'))
        self.ledger.fail(first,'SimulatedStop')
        self.assertIsNotNone(self.ledger.claim('w2'))

    def test_cannot_fabricate_model_receipt_via_queue_finish(self):
        self.submit()
        ticket=self.ledger.claim('w1');self.ledger.start(ticket)
        fake={'session':'chat1','request_id':'ask1','request_sha256':self.spec().request().bound_digest(),
              'model_sha256':M,'tokenizer_sha256':T,'principal':self.identity.key(),
              'revision':1,'output_sha256':'c'*64}
        with self.assertRaises(FlightConflict):self.ledger.finish(ticket,fake,spine=self.spine)
        self.assertEqual(self.ledger.inspect('job1')['state'],'running')
        self.assertEqual(self.backend.calls,0)

    def test_receipt_conflict_after_actual_inference_is_refused(self):
        self.submit();ticket=self.ledger.claim('w1');self.ledger.start(ticket)
        good=self.spine.turn('chat1','ask1','Explain idea 1')
        bad=dict(good,output_sha256='c'*64)
        with self.assertRaises(FlightConflict):self.ledger.finish(ticket,bad,spine=self.spine)
        self.assertEqual(self.ledger.inspect('job1')['state'],'running')

    def test_event_outbox_deletion_detected(self):
        self.submit()
        self.db._db.execute("DELETE FROM outbox WHERE stream='job1'")
        with self.assertRaises(FlightConflict):inspect(self.ledger)
        with self.assertRaises(FlightConflict):self.ledger.submit(self.spec())

    def test_event_chain_valid_hash_with_invalid_transition_detected(self):
        self.submit()
        self.db._db.execute("UPDATE ai_flight_jobs SET state='completed',receipt_json=?,receipt_sha256=? WHERE job_id='job1'",(b'{}',sha256(b'{}').hexdigest()))
        with self.assertRaises(FlightConflict):inspect(self.ledger)

    def test_operator_combines_diagnostic_and_recovery(self):
        op=FlightOperator(self.ledger,self.spine)
        op.enqueue([self.spec(1),self.spec(2)])
        status=op.diagnose()
        self.assertEqual(status['integrity']['states']['queued'],2)
        with self.assertRaises(FlightConflict):op.pause()
        op.pause(approved=True)
        self.assertEqual(op.diagnose()['watchdog']['mode'],'paused')
        op.resume(approved=True)

    def test_cancel_running_twice_does_not_flood_audit(self):
        self.submit()
        t=self.ledger.claim('w1');self.ledger.start(t)
        self.ledger.cancel('job1')
        first=inspect(self.ledger)['events']
        self.ledger.cancel('job1')
        self.assertEqual(inspect(self.ledger)['events'],first)
