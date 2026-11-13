"""Offline publisher: actual SQLite outbox, private immutable files and crash replay."""
from __future__ import annotations
from pathlib import Path
from hashlib import sha256
import os
import stat
import tempfile
import unittest
from unittest.mock import patch
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.principal import create_session
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import outbox
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.ledger import FlightLedger
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.contracts import FlightSpec
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery import PrivateEventSink,DeliveryPump
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.contracts import DeliveryHeld,DeliveryPolicy
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.projection import encode
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.verify import verify_saved_receipt

HASH='a'*64

class LocalDeliveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='ai-delivery-',dir=Path.home())
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        state=self.root/'state';state.mkdir(mode=0o700)
        self.spool=self.root/'spool';self.spool.mkdir(mode=0o700)
        self.db=SpineDatabase(state);self.addCleanup(self.db.close)
        self.identity=Identity('t','u',HASH,HASH)
        self.ledger=FlightLedger(self.db,self.identity)
        with self.db.transaction() as conn:create_session(conn,self.identity,'s1')
        self.ledger.submit(FlightSpec(self.identity,'job1','s1','r1',
            'TOP SECRET original prompt should not leave SQLite'))
        self.sink=PrivateEventSink(self.spool);self.addCleanup(self.sink.close)
        self.pump=DeliveryPump(self.ledger,self.sink)
    def events(self):
        with self.db.snapshot() as conn:return outbox.pending(conn,limit=32)
    def first(self):
        return next(x for x in self.events() if x['kind']=='ai_flight')
    def files(self):return list(self.spool.glob('*.event'))

    def test_first_submission_materializes_one_immutable_receipt(self):
        proof=self.pump.drain(limit=4)
        self.assertEqual(proof['count'],1)
        self.assertEqual(len(self.files()),1)
        self.assertEqual(proof['model_calls'],0)
        self.assertNotIn(b'TOP SECRET',self.files()[0].read_bytes())

    def test_file_permissions_and_identity_name(self):
        self.pump.drain()
        f=self.files()[0]
        self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o600)
        self.assertEqual(f.name,sha256(self.first_id().encode('ascii')).hexdigest()+'.event')
    def first_id(self):
        with self.db.snapshot() as conn:
            return conn.execute("SELECT event_key FROM outbox WHERE kind='ai_flight'").fetchone()[0]

    def test_no_duplicate_file_after_second_drain(self):
        self.pump.drain();before=self.files()[0].read_bytes()
        self.assertEqual(self.pump.drain()['count'],0)
        self.assertEqual(self.files()[0].read_bytes(),before)

    def test_crash_between_publication_and_ack_replays_exact_file(self):
        item=self.first()
        self.sink.append(item)
        self.assertEqual(len(self.files()),1)
        self.assertTrue(self.pump.drain()['replayed'])
        self.assertEqual(len(self.files()),1)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute('SELECT acked FROM outbox WHERE event_key=?',(item['event_key'],)).fetchone(),(1,))

    def test_partial_file_never_overwritten_or_acked(self):
        item=self.first();filename,raw,_=encode(item)
        (self.spool/filename).write_bytes(raw[:20])
        with self.assertRaises(DeliveryHeld):self.pump.drain()
        with self.db.snapshot() as conn:self.assertEqual(conn.execute('SELECT acked FROM outbox').fetchone(),(0,))
        self.assertEqual((self.spool/filename).read_bytes(),raw[:20])

    def test_mutated_existing_receipt_fails_closed(self):
        self.pump.drain();p=self.files()[0]
        p.write_bytes(p.read_bytes().replace(b'job1',b'jobX'))
        self.assertRaises(DeliveryHeld,self.sink.inventory)

    def test_external_symlink_receipt_rejected(self):
        item=self.first();filename,_,_=encode(item)
        outside=self.root/'outside';outside.write_text('NO TOUCH')
        (self.spool/filename).symlink_to(outside)
        with self.assertRaises((DeliveryHeld,OSError)):self.pump.drain()
        self.assertEqual(outside.read_text(),'NO TOUCH')

    def test_group_world_open_spool_refused(self):
        self.sink.close();self.spool.chmod(0o755)
        self.assertRaises(Exception,PrivateEventSink,self.spool)
        self.spool.chmod(0o700)

    def test_spool_symlink_root_refused(self):
        link=self.root/'link';link.symlink_to(self.spool)
        self.assertRaises(Exception,PrivateEventSink,link)

    def test_zero_width_noop_not_emitted(self):
        with self.assertRaises(DeliveryHeld):self.pump.drain(limit=0)

    def test_inconsistent_payload_digest_refused(self):
        item=dict(self.first());item['event_sha256']='b'*64
        self.assertRaises(DeliveryHeld,self.sink.append,item)

    def test_prompt_field_is_not_allowed_in_delivery(self):
        item=dict(self.first());item['payload']=dict(item['payload'],prompt='secret')
        self.assertRaises(DeliveryHeld,self.sink.append,item)

    def test_unexpected_event_kind_refused(self):
        item=dict(self.first());item['kind']='untrusted_tool'
        self.assertRaises(DeliveryHeld,self.sink.append,item)

    def test_delivery_integrity_before_ack(self):
        item=self.first();original=self.sink.append(item)
        self.assertTrue(self.sink.verify(item)['verified'])
        self.assertEqual(original['delivery_sha256'],sha256(self.files()[0].read_bytes()).hexdigest())
        self.assertEqual(self.sink.inventory()['files'],1)

    def test_idempotent_new_event_after_first_delivery(self):
        self.pump.drain()
        self.ledger.cancel('job1')
        result=self.pump.drain()
        self.assertEqual(result['count'],1)
        self.assertEqual(len(self.files()),2)
        self.assertEqual(self.sink.inventory()['files'],2)

    def test_wrong_principal_fails_without_ack(self):
        other=FlightLedger(self.db,Identity('other','u',HASH,HASH))
        with self.assertRaises(Exception):DeliveryPump(other,self.sink).drain()
        with self.db.snapshot() as conn:self.assertEqual(conn.execute('SELECT acked FROM outbox').fetchone(),(0,))

    def test_spool_archive_verifier_refuses_wrong_name(self):
        item=self.first();name,raw,_=encode(item)
        self.assertRaises(DeliveryHeld,verify_saved_receipt,raw,'f'*64+'.event')

    def test_spool_archive_verifier_accepts_exact_bytes(self):
        item=self.first();name,raw,_=encode(item)
        self.assertTrue(verify_saved_receipt(raw,name)['verified'])

    def test_outbox_corruption_fails_without_publication(self):
        with self.db.transaction() as conn:conn.execute('UPDATE outbox SET event_sha256=?',('b'*64,))
        with self.assertRaises(Exception):self.pump.drain()
        self.assertEqual(self.files(),[])

    def test_source_event_writer_cannot_double_spool(self):
        event=self.first()
        first=self.sink.append(event);second=self.sink.append(event)
        self.assertFalse(first['replayed']);self.assertTrue(second['replayed'])
        self.assertEqual(len(self.files()),1)

    def test_no_untracked_file_in_inventory(self):
        (self.spool/'unexpected.txt').write_text('bad')
        self.assertRaises(DeliveryHeld,self.sink.inventory)

    def test_oversized_or_bool_operator_limit_refused(self):
        for value in (-1,0,129,True):
            with self.subTest(value=value),self.assertRaises(DeliveryHeld):self.pump.drain(limit=value)

    def test_closed_spool_cannot_publish(self):
        self.sink.close();self.assertRaises(DeliveryHeld,self.sink.append,self.first())

    def test_unapproved_private_memory_kind_not_exported(self):
        with self.db.transaction() as conn:
            outbox.emit(conn,'memory_s1','s1','memory',{'content':'not allowed'})
        proof=self.pump.drain()
        self.assertEqual(proof['count'],1)
        self.assertNotIn(b'not allowed',self.files()[0].read_bytes())

    def test_fresh_spool_has_empty_inventory(self):
        self.assertEqual(self.sink.inventory()['files'],0)

if __name__=='__main__':unittest.main()
