"""Local serving placement and replay cursors without provider calls."""
from __future__ import annotations
import time,unittest
from skeleton.ai.runtime.operational_ai.model.distributed.workers import Worker,WorkerRegistry,WorkerError
from skeleton.ai.runtime.operational_ai.model.distributed.placement import PlacementRequest,place
from skeleton.ai.runtime.operational_ai.model.distributed.fence import WorkerFences
from skeleton.ai.runtime.operational_ai.model.distributed.queues import TenantFairQueue
from skeleton.ai.runtime.operational_ai.model.distributed.batch import BatchPlanner
from skeleton.ai.runtime.operational_ai.model.distributed.pressure import Pressure,assess_pressure
from skeleton.ai.runtime.operational_ai.transport.live.cursor import CursorSigner,EventCursor,CursorError
from skeleton.ai.runtime.operational_ai.transport.live.replay import EventReplay
from skeleton.ai.runtime.operational_ai.persistence.journal import EventJournal

class TestServing(unittest.TestCase):
    def test_placement_pins_identity_and_memory(self):
        worker=Worker('worker','a'*64,'b'*64,1,1000,10,999_999_999,100,'ready','local-host')
        req=PlacementRequest('a'*64,'b'*64,100,1000,500,'req')
        self.assertEqual(place(req,(worker,)).worker_id,'worker')
        self.assertFalse(place(PlacementRequest('z'*64,'b'*64,100,100,500,'r'),(worker,)).accepted)

    def test_worker_epoch_and_heartbeat(self):
        registry=WorkerRegistry(timeout_ns=1_000_000)
        worker=Worker('id','a'*64,'b'*64,1,1000,0,100000,100,'ready','local-host')
        registry.heartbeat(worker)
        self.assertEqual(len(registry.candidates(now_ns=100_050)),1)
        self.assertEqual(len(registry.candidates(now_ns=2_000_000)),0)
        with self.assertRaises(WorkerError):registry.heartbeat(worker)

    def test_leases_refuse_epoch_reuse(self):
        leases=WorkerFences();leases.reset('w',1)
        first=leases.admit('w',1,'r',100)
        self.assertTrue(leases.verify(first))
        leases.reset('w',2)
        self.assertFalse(leases.verify(first))
        with self.assertRaises(WorkerError):leases.release(first)

    def test_fair_queue_and_batching(self):
        q=TenantFairQueue()
        q.put('a','r1','c'*64,100);q.put('a','r2','c'*64,100)
        q.put('b','r3','c'*64,300)
        jobs=tuple(q.pop() for _ in range(3))
        self.assertEqual([j.tenant for j in jobs],['a','b','a'])
        grouped=BatchPlanner(max_jobs=2,max_tokens=500).group(jobs)
        self.assertEqual(sum(b.total_tokens for b in grouped),500)

    def test_unknown_pressure_is_fail_closed(self):
        self.assertEqual(assess_pressure(Pressure(None,None,None)).mode,'blocked')
        self.assertEqual(assess_pressure(Pressure(.5,.6,0)).mode,'normal')
        self.assertEqual(assess_pressure(Pressure(.99,.6,0)).mode,'blocked')

    def test_scope_bound_cursor(self):
        signer=CursorSigner(b's'*32)
        cursor=EventCursor('session','tenant','user',0,'0'*64,time.time_ns()+1000000000)
        token=signer.issue(cursor)
        self.assertEqual(signer.verify(token,session='session',tenant='tenant',user='user'),cursor)
        with self.assertRaises(CursorError):signer.verify(token,session='other',tenant='tenant',user='user')
        with self.assertRaises(CursorError):signer.verify(token[:-3]+'xyz',session='session',tenant='tenant',user='user')

    def test_journal_paged_replay(self):
        with EventJournal(':memory:') as journal:
            journal.append(stream='session',event_id='e1',kind='test',payload={'item':1})
            journal.append(stream='session',event_id='e2',kind='test',payload={'item':2})
            replay=EventReplay(journal,CursorSigner(b'k'*32),max_page=1)
            first=replay.page(session='session',tenant='tenant',user='user',limit=1)
            self.assertTrue(first.has_more)
            second=replay.page(session='session',tenant='tenant',user='user',cursor=first.next_cursor,limit=1)
            self.assertFalse(second.has_more)
            self.assertEqual(second.events[0]['seq'],2)
            self.assertEqual(second.events[0]['previous'],first.events[0]['sha256'])

if __name__=='__main__':unittest.main()
