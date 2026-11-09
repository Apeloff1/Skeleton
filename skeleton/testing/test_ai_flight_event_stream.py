"""Adversarial acceptance of bounded SSE over real SQLite flight custody.

Uses only original fake job text; no real GGUF is claimed. The actual
flight-event chain, outbox, principal and HTTP bearer boundaries are exercised.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import http.client

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.principal import create_session
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.contracts import FlightSpec,FlightConflict
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.ledger import FlightLedger
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.cursor import CursorAuthority
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.service import EventStream
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.contracts import (
    StreamError,InvalidCursor,StreamConflict,StreamPolicy,StreamUnavailable)
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.client import parse_stream,get_events
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.poller import read_until
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.query import parse_path,StreamQuery
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.render import encode
from skeleton.ai.runtime.operational_ai.transport.flight.dispatch import FlightDispatcher
from skeleton.ai.runtime.operational_ai.transport.flight.http import FlightHTTPServer

BEARER='a-very-long-independent-operator-bearer-token-with-32-chars'
HASH='a'*64

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='flight-events-',dir=Path.home())
        self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name)/'private'
        self.directory.mkdir(mode=0o700)
        self.db=SpineDatabase(self.directory);self.addCleanup(self.db.close)
        self.id=Identity('tenant','operator',HASH,HASH)
        self.ledger=FlightLedger(self.db,self.id)
        self.session='sess1'
        with self.db.transaction() as conn:create_session(conn,self.id,self.session)
        self.spec=FlightSpec(self.id,'job1',self.session,'req1',
            'a PRIVATE prompt that must never appear in event delivery')
        self.ledger.submit(self.spec)
        self.svc=EventStream(self.ledger,BEARER)

    def snap(self,cursor=None,limit=32):
        return self.svc.reader.read('job1',cursor,limit=limit)

    def test_first_event_is_verified_submission(self):
        one=self.snap()
        self.assertEqual(one.state,'queued')
        self.assertEqual([e.kind for e in one.events],['submitted'])
        self.assertEqual(one.latest_ordinal,1)
        self.assertFalse(one.terminal)

    def test_no_model_text_or_prompt_in_sse(self):
        data,_=self.svc.read(StreamQuery('job1',None,32,0))
        self.assertNotIn(b'PRIVATE prompt',data)
        self.assertNotIn(b'operator',data)
        self.assertIn(b'event: transition',data)
        self.assertIn(b'event: checkpoint',data)

    def test_cursor_roundtrip_and_empty_resumption(self):
        first=self.snap();second=self.snap(first.next_cursor)
        self.assertEqual(second.events,())
        self.assertEqual(second.next_cursor,first.next_cursor)
        self.assertFalse(second.backlog)

    def test_cursor_hmac_survives_restart(self):
        original=self.snap()
        restarted=EventStream(self.ledger,BEARER)
        result=restarted.reader.read('job1',original.next_cursor)
        self.assertEqual(result.events,())
        self.assertEqual(result.state,'queued')

    def test_cursor_rejected_with_wrong_bearer(self):
        cursor=self.snap().next_cursor
        self.assertRaises(InvalidCursor,EventStream(self.ledger,'b'*40).reader.read,'job1',cursor)

    def test_cursor_job_binding(self):
        spec=FlightSpec(self.id,'job2',self.session,'req2','Another private question')
        self.ledger.submit(spec)
        self.assertRaises(InvalidCursor,self.svc.reader.read,'job2',self.snap().next_cursor)

    def test_cursor_principal_binding(self):
        other=CursorAuthority(BEARER,'another-principal')
        self.assertRaises(InvalidCursor,other.decode,'job1',self.snap().next_cursor)

    def test_cursor_tamper_fails_without_stream(self):
        cursor=self.snap().next_cursor
        corrupted=cursor[:-1]+('a' if cursor[-1]!='a' else 'b')
        self.assertRaises(InvalidCursor,self.svc.reader.read,'job1',corrupted)

    def test_cursor_ordinal_future_refused(self):
        cursor=self.svc.reader.cursors.encode('job1',23,HASH)
        self.assertRaises(StreamConflict,self.svc.reader.read,'job1',cursor)

    def test_cursor_valid_mac_wrong_chain_digest_rejected(self):
        cursor=self.svc.reader.cursors.encode('job1',1,'b'*64)
        self.assertRaises(StreamConflict,self.svc.reader.read,'job1',cursor)

    def test_pagination_reconnect_after_state_changes(self):
        ticket=self.ledger.claim('worker1')
        self.assertIsNotNone(ticket)
        events=self.snap(limit=1)
        self.assertEqual(events.events[0].ordinal,1)
        self.assertTrue(events.backlog)
        two=self.snap(events.next_cursor,limit=1)
        self.assertEqual(two.events[0].ordinal,2)
        self.assertEqual(two.events[0].kind,'claimed')
        self.assertFalse(two.backlog)
        self.ledger.cancel('job1')
        third=self.snap(two.next_cursor)
        self.assertEqual(third.state,'cancelled')
        self.assertTrue(third.terminal)
        self.assertEqual(third.events[0].kind,'cancelled')

    def test_outbox_loss_fails_closed(self):
        with self.db.transaction() as conn:conn.execute('DELETE FROM outbox')
        with self.assertRaises(Exception):self.snap()

    def test_changed_chain_event_fails_closed(self):
        with self.db.transaction() as conn:conn.execute('UPDATE ai_flight_events SET event_json=?',(b'{}',))
        with self.assertRaises(Exception):self.snap()

    def test_job_state_divergence_fails_closed(self):
        with self.db.transaction() as conn:conn.execute("UPDATE ai_flight_jobs SET state='held' WHERE job_id='job1'")
        with self.assertRaises(Exception):self.snap()

    def test_wrong_principal_has_no_events(self):
        stranger=FlightLedger(self.db,Identity('stranger','operator',HASH,HASH))
        with self.assertRaises(FlightConflict):EventStream(stranger,BEARER).reader.read('job1')

    def test_bounded_long_poll_returns_immediately_on_event(self):
        first=self.snap()
        timer=time.monotonic()
        value=read_until(self.svc.reader,'job1',first.next_cursor,wait_ms=35)
        self.assertEqual(value.events,())
        self.assertLess(time.monotonic()-timer,0.6)

    def test_long_poll_observes_state_change(self):
        old=self.snap()
        def mutate():
            time.sleep(.035)
            self.ledger.cancel('job1')
        t=threading.Thread(target=mutate);t.start()
        try:value=read_until(self.svc.reader,'job1',old.next_cursor,wait_ms=450)
        finally:t.join(timeout=2)
        self.assertEqual(value.events[0].kind,'cancelled')
        self.assertTrue(value.terminal)

    def test_stream_framing_exact_checksum(self):
        body=encode(self.snap())
        rows=parse_stream(body)
        self.assertEqual(rows[0]['type'],'transition')
        self.assertEqual(rows[-1]['type'],'checkpoint')
        self.assertEqual(rows[0]['cursor'],rows[-1]['cursor'])
        self.assertEqual(rows[-1]['data']['model_calls'],0)

    def test_stream_truncation_rejected(self):
        body=encode(self.snap())
        self.assertRaises(StreamError,parse_stream,body[:-1])

    def test_stream_duplicated_checkpoint_rejected(self):
        body=encode(self.snap())
        checkpoint=body.split(b'event: checkpoint')[1]
        self.assertRaises(StreamError,parse_stream,body+b'event: checkpoint'+checkpoint)

    def test_stream_invalid_cursor_rejected(self):
        self.assertRaises(StreamError,parse_stream,b'id: injected\nevent: checkpoint\ndata: {}\n\n')

    def test_stream_invalid_event_kind_rejected(self):
        self.assertRaises(StreamError,parse_stream,b'event: jailbreak\ndata: {}\n\n')

    def test_noncanonical_uri_rejected(self):
        for s in ('/v2/jobs/%6aob1/events','http://localhost/v2/jobs/job1/events',
                  '/v2/jobs/job1/events?wait_ms=2001','/v2/jobs/job1/events?limit=0',
                  '/v2/jobs/job1/events?cursor=','/v2/jobs/job1/events?wait_ms=01',
                  '/v2/jobs/job1/events?wait_ms=1&wait_ms=2',
                  '/v2/jobs/job1/events?unexpected=1','/v2/jobs/job1/events#frag',
                  '/v2/jobs/job1/events?limit=9999'):
            with self.subTest(s=s),self.assertRaises(StreamError):parse_path(s)

    def test_uri_canonical_minimal(self):
        q=parse_path('/v2/jobs/job1/events?limit=2&wait_ms=10')
        self.assertEqual((q.job_id,q.limit,q.wait_ms),('job1',2,10))

    def test_invalid_policy_holds(self):
        for n in (0,65,True):
            with self.subTest(n=n),self.assertRaises(StreamError):StreamPolicy(max_events=n)

    def test_invalid_scope_or_secret(self):
        for token in ('tiny','a'*513,'a'*40+'\n'):
            with self.subTest(token=token[:5]),self.assertRaises(InvalidCursor):CursorAuthority(token,self.id.key())

    def test_read_only_no_model_generation(self):
        before=self.ledger.state_count()
        self.svc.read(StreamQuery('job1',None,32,0))
        self.assertEqual(self.ledger.state_count(),before)
        with self.db.snapshot() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM turns').fetchone()[0],0)

    def start_server(self,token=BEARER):
        app=SimpleNamespace(spine=SimpleNamespace(identity=self.id),
            ledger=self.ledger,worker=SimpleNamespace(ledger=self.ledger))
        dispatcher=FlightDispatcher(app)
        srv=FlightHTTPServer(('127.0.0.1',0),dispatcher,token)
        self.addCleanup(srv.server_close)
        thread=threading.Thread(target=srv.serve_forever,kwargs={'poll_interval':0.02},daemon=True)
        thread.start();self.addCleanup(srv.shutdown);self.addCleanup(lambda:thread.join(timeout=2))
        return srv

    def test_advertised_protocol_contains_finite_event_route(self):
        srv=self.start_server()
        conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=2)
        try:
            conn.request('GET','/v2/protocol',headers={'Authorization':'Bearer '+BEARER})
            resp=conn.getresponse()
            self.assertEqual(resp.status,200)
            value=json.loads(resp.read())
            self.assertIn('event_stream',str(value))
        finally:conn.close()

    def test_http_authenticated_event_get(self):
        srv=self.start_server();port=srv.server_port
        items=get_events(port=port,token=BEARER,job_id='job1')
        self.assertEqual(items[0]['data']['kind'],'submitted')
        self.assertEqual(items[-1]['data']['state'],'queued')

    def test_http_no_bearer_denied(self):
        srv=self.start_server();conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=2)
        try:
            conn.request('GET','/v2/jobs/job1/events')
            response=conn.getresponse();self.assertEqual(response.status,401);response.read()
        finally:conn.close()

    def test_http_wrong_origin_denied(self):
        srv=self.start_server();conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=2)
        try:
            conn.request('GET','/v2/jobs/job1/events',headers={
                'Authorization':'Bearer '+BEARER,'Origin':'https://evil.invalid'})
            response=conn.getresponse();self.assertEqual(response.status,403);response.read()
        finally:conn.close()

    def test_http_wrong_job_cursor_denied(self):
        srv=self.start_server();cursor=self.snap().next_cursor
        conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=2)
        try:
            conn.request('GET','/v2/jobs/job2/events?cursor='+cursor,headers={
                'Authorization':'Bearer '+BEARER})
            response=conn.getresponse();self.assertEqual(response.status,400);response.read()
        finally:conn.close()

    def test_http_canonical_404_route(self):
        srv=self.start_server();conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=2)
        try:
            conn.request('GET','/v2/unknown',headers={'Authorization':'Bearer '+BEARER})
            resp=conn.getresponse();self.assertEqual(resp.status,404);resp.read()
        finally:conn.close()

    def test_http_get_body_framing_refused(self):
        srv=self.start_server();conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=2)
        try:
            conn.request('GET','/v2/jobs/job1/events',headers={'Authorization':'Bearer '+BEARER,'Content-Length':'1'})
            resp=conn.getresponse();self.assertEqual(resp.status,400);resp.read()
        finally:conn.close()

    def test_http_corrupt_chain_reports_held(self):
        srv=self.start_server()
        with self.db.transaction() as conn:conn.execute('DELETE FROM outbox')
        conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=2)
        try:
            conn.request('GET','/v2/jobs/job1/events',headers={'Authorization':'Bearer '+BEARER})
            resp=conn.getresponse();self.assertEqual(resp.status,503);resp.read()
        finally:conn.close()

if __name__=='__main__':unittest.main()
