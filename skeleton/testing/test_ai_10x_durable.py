"""Operation history, fencing, restart snapshots, inbox/outbox and fail-closed replay."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.persistence.durable.database import DurableDatabase,DurableError
from skeleton.ai.runtime.operational_ai.persistence.durable.operations import OperationRepository
from skeleton.ai.runtime.operational_ai.persistence.durable.leases import DurableLeases
from skeleton.ai.runtime.operational_ai.persistence.durable.eventlog import OperationEvents
from skeleton.ai.runtime.operational_ai.persistence.durable.outbox import TransactionalOutbox
from skeleton.ai.runtime.operational_ai.persistence.durable.snapshots import OperationSnapshots
from skeleton.ai.runtime.operational_ai.persistence.durable.idempotency import RequestDedupe
from skeleton.ai.runtime.operational_ai.persistence.durable.doctor import inspect

class TestDurable(unittest.TestCase):
    def setUp(self):
        self.db=DurableDatabase()
        self.repo=OperationRepository(self.db)
        self.repo.create('tenant','user','op',{'question':'hello'})
    def tearDown(self):self.db.close()

    def test_create_replay_and_cas(self):
        same=self.repo.create('tenant','user','op',{'question':'hello'})
        self.assertEqual(same.version,1)
        first=self.repo.change('tenant','user','op',expected_version=1,state='running')
        self.assertEqual(first.version,2)
        with self.assertRaises(DurableError):
            self.repo.change('tenant','user','op',expected_version=1,state='succeeded',result={})
        done=self.repo.change('tenant','user','op',expected_version=2,state='succeeded',result={'text':'ok'})
        self.assertEqual(done.result['text'],'ok')
        with self.assertRaises(DurableError):
            self.repo.change('tenant','user','op',expected_version=3,state='running')

    def test_conflicting_request_fails(self):
        with self.assertRaises(DurableError):
            self.repo.create('tenant','user','op',{'question':'different'})

    def test_event_chain_and_checkpoint(self):
        events=OperationEvents(self.db)
        first=events.append('tenant','user','op','event_1','admitted',{'x':1})
        second=events.append('tenant','user','op','event_2','running',{'x':2})
        self.assertEqual(second.previous,first.digest)
        self.assertEqual(len(events.replay('tenant','user','op')),2)
        snapshots=OperationSnapshots(self.db)
        saved=snapshots.save('tenant','user','op',{'rev':2})
        self.assertEqual(snapshots.load_verified('tenant','user','op'),(2,{'rev':2}))
        self.assertEqual(inspect(self.db)['status'],'verified')

    def test_event_collision(self):
        events=OperationEvents(self.db)
        events.append('tenant','user','op','event_1','admitted',{'x':1})
        with self.assertRaises(DurableError):
            events.append('tenant','user','op','event_1','admitted',{'x':2})

    def test_stale_lease_refused(self):
        clock=[1_000_000_000]
        leases=DurableLeases(self.db,clock=lambda:clock[0])
        first=leases.acquire('model','worker',100_000_000)
        with self.assertRaises(DurableError):leases.acquire('model','other',100_000_000)
        clock[0]+=200_000_000
        second=leases.acquire('model','other',100_000_000)
        self.assertGreater(second.fence,first.fence)
        with self.assertRaises(DurableError):leases.renew(first,100_000_000)
        self.assertTrue(leases.validate(second))

    def test_inbox_idempotency(self):
        out=TransactionalOutbox(self.db)
        self.assertTrue(out.inbox_accept('consumer','event',{'x':1}))
        self.assertFalse(out.inbox_accept('consumer','event',{'x':1}))
        with self.assertRaises(DurableError):out.inbox_accept('consumer','event',{'x':2})

    def test_outbox_claim_ack_and_retry(self):
        out=TransactionalOutbox(self.db)
        self.assertTrue(out.enqueue('tenant','user','op','msg1','offline',{'text':'hello'}))
        self.assertFalse(out.enqueue('tenant','user','op','msg1','offline',{'text':'hello'}))
        msg=out.pending(now_ns=0)[0]
        claimed=out.claim(msg)
        self.assertEqual(claimed.fence,1)
        with self.assertRaises(DurableError):out.claim(msg)
        out.ack(claimed)
        self.assertEqual(len(out.pending(now_ns=0)),0)

    def test_replay_idempotency_different_fingerprint_fails(self):
        cache=RequestDedupe(self.db)
        self.assertEqual(cache.record('scope','request',{'text':'hello'},{'ok':1}),({'ok':1},False))
        self.assertEqual(cache.record('scope','request',{'text':'hello'},{'ok':2}),({'ok':1},True))
        with self.assertRaises(DurableError):cache.record('scope','request',{'text':'changed'},{'ok':2})

    def test_cross_tenant_visibility(self):
        with self.assertRaises(DurableError):self.repo.get('other','user','op')
        self.assertEqual(self.repo.list_active('other','user'),())

if __name__=='__main__':unittest.main()
