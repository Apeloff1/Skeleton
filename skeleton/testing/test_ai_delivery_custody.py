"""Private event spool, SQLite ack and principal binding under real filesystem custody."""
from __future__ import annotations
import unittest, tempfile, os
from pathlib import Path
from hashlib import sha256
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.principal import create_session
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.ledger import FlightLedger
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.contracts import FlightSpec
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery import PrivateEventSink,DeliveryPump,read_since
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.contracts import DeliveryHeld

D=sha256(b'fixture-model').hexdigest()
class CustodyTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(dir=Path.home());self.addCleanup(t.cleanup)
        self.root=Path(t.name);state=self.root/'state';state.mkdir(mode=0o700)
        self.spool=self.root/'spool';self.spool.mkdir(mode=0o700)
        self.db=SpineDatabase(state);self.addCleanup(self.db.close)
        self.identity=Identity('t','u',D,D)
        self.ledger=FlightLedger(self.db,self.identity)
        with self.db.transaction() as conn:create_session(conn,self.identity,'s1')
        self.ledger.submit(FlightSpec(self.identity,'job1','s1','r1','private: DO NOT EXPORT'))
        self.sink=PrivateEventSink(self.spool);self.addCleanup(self.sink.close)
        self.pump=DeliveryPump(self.ledger,self.sink)

    def test_owner_created_and_content_private(self):
        owner=self.spool/'.spool.owner'
        self.assertTrue(owner.is_file());self.assertEqual(owner.stat().st_mode&0o077,0)
        self.assertNotIn(b'private:',owner.read_bytes())
    def test_acked_files_verified_across_restart(self):
        self.pump.drain();self.sink.close()
        with PrivateEventSink(self.spool) as again:
            audit=DeliveryPump(self.ledger,again).audit()
        self.assertEqual(audit['acknowledged'],1)
        self.assertEqual(audit['published_receipts'],1)
    def test_principal_adoption_refused(self):
        other=Identity('t','other-user',D,D)
        with PrivateEventSink(self.spool) as again:
            with self.assertRaises(DeliveryHeld):DeliveryPump(FlightLedger(self.db,other),again)
    def test_model_adoption_refused(self):
        other=Identity('t','u','b'*64,D)
        with PrivateEventSink(self.spool) as again:
            with self.assertRaises(DeliveryHeld):DeliveryPump(FlightLedger(self.db,other),again)
    def test_unbound_nonempty_spool_refused(self):
        t=self.root/'foreign';t.mkdir(mode=0o700)
        (t/'old.event').write_text('unknown')
        with PrivateEventSink(t) as other:
            with self.assertRaises(DeliveryHeld):DeliveryPump(self.ledger,other)
    def test_corrupt_owner_marker_refuses_export(self):
        self.pump.drain()
        marker=self.spool/'.spool.owner'
        marker.write_bytes(marker.read_bytes().replace(b'"u"',b'"x"'))
        self.assertRaises(DeliveryHeld,self.pump.drain)
    def test_missing_acked_receipt_blocks_next_export(self):
        self.pump.drain()
        f=next(self.spool.glob('*.event'));f.unlink()
        self.ledger.cancel('job1')
        self.assertRaises(DeliveryHeld,self.pump.drain)
        self.assertEqual(list(self.spool.glob('*.event')),[])
    def test_tampered_acked_receipt_blocks(self):
        self.pump.drain();f=next(self.spool.glob('*.event'))
        f.write_bytes(f.read_bytes().replace(b'job1',b'job2'))
        self.assertRaises(DeliveryHeld,self.pump.audit)
    def test_crash_published_but_unacked_auditable(self):
        with self.db.snapshot() as conn:
            from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.outbox import pending
            record=pending(conn)[0]
        self.sink.append(record)
        proof=self.pump.audit()
        self.assertEqual(proof['unacknowledged_published'],1)
        self.assertEqual(self.pump.drain()['replayed'],1)
    def test_orphaned_valid_receipt_without_sqlite_refused(self):
        self.pump.drain()
        with self.db.transaction() as conn:
            conn.execute('DELETE FROM outbox WHERE kind=?',('ai_flight',))
        self.assertRaises(DeliveryHeld,self.pump.audit)
    def test_source_event_tamper_refuses_export(self):
        self.pump.drain()
        with self.db.transaction() as conn:
            conn.execute('UPDATE outbox SET event_sha256=?',('f'*64,))
        self.assertRaises(DeliveryHeld,self.pump.audit)
    def test_consumer_cursor_restarts_at_zero(self):
        self.pump.drain();read=read_since(self.ledger,self.sink,sequence=0)
        self.assertEqual(len(read['events']),1)
        self.assertFalse(read['contains_model_text'])
        self.assertTrue(read['next_sequence']>0)
        self.assertEqual(len(read_since(self.ledger,self.sink,sequence=read['next_sequence'])['events']),0)
    def test_consumer_does_not_expose_pre_ack_event(self):
        self.assertEqual(len(read_since(self.ledger,self.sink,sequence=0)['events']),0)
    def test_consumer_detects_ack_but_missing_file(self):
        self.pump.drain()
        next(self.spool.glob('*.event')).unlink()
        self.assertRaises((DeliveryHeld,FileNotFoundError),read_since,self.ledger,self.sink,sequence=0)
    def test_invalid_cursor_and_limit(self):
        for seq in (-1,True,2**64,'1'):
            with self.subTest(seq=seq),self.assertRaises(DeliveryHeld):
                read_since(self.ledger,self.sink,sequence=seq)
        self.assertRaises(DeliveryHeld,read_since,self.ledger,self.sink,limit=True)
    def test_new_job_transition_after_first_export(self):
        self.pump.drain();self.ledger.cancel('job1')
        self.pump.drain()
        record=read_since(self.ledger,self.sink)
        self.assertEqual(len(record['events']),2)
        self.assertEqual(record['events'][0]['kind'],'ai_flight')
        self.assertTrue(record['next_sequence']>record['events'][0]['sequence'])

if __name__=='__main__':unittest.main()
