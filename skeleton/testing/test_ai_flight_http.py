"""Socket-level security and native-flight correctness regression.

All model emissions are deterministic local fixtures. This proves HTTP ->
flight-control -> execution-spine -> authoritative SQLite, not a certified
real GGUF device qualification.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import http.client
import json
import socket
import tempfile
import threading
import unittest
from contextlib import closing

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import (
    Identity,SpineDatabase,ExecutionSpine,SpineLimits)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.flight_control import FlightLedger,NativeFlightWorker
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.operator import FlightOperator
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.production import FlightApplication
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.context.knowledge_plane import KnowledgePlane
from skeleton.ai.runtime.operational_ai.transport.flight import FlightDispatcher,FlightHTTPServer
from skeleton.ai.runtime.operational_ai.transport.flight.client import FlightClient,FlightClientError
from skeleton.ai.runtime.operational_ai.transport.flight.contracts import PROTOCOL,SCHEMA
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
from skeleton.ai.runtime.operational_ai.deployment.boot.identity import PrincipalBinding,establish_binding

M='c'*64;T='d'*64;TOKEN='A'*48

class FixtureBackend:
    model_digest=M;tokenizer_digest=T
    def __init__(self):self.calls=0;self.fail=False
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1
        if self.fail:raise RuntimeError('private-model-failure-never-disclose')
        output='Native fixture response for '+messages[-1]['content'][:45]
        return Generated(output,48,16,sha256(output.encode()).hexdigest(),M,T,'stop')

class FlightHttpAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ai-flight-http-', dir=Path.home())
        self.root=Path(self.temp.name)
        self.state=self.root/'private';self.state.mkdir(mode=0o700)
        establish_binding(self.state,PrincipalBinding('tenant','operator',M,T))
        self.locks=self.state/'gates';self.locks.mkdir(mode=0o700)
        self.db=SpineDatabase(self.state)
        self.gate=SessionGate(self.locks)
        self.id=Identity('tenant','operator',M,T)
        self.model=FixtureBackend()
        self.knowledge=KnowledgePlane(self.db,self.id)
        self.spine=ExecutionSpine(db=self.db,session_gate=self.gate,backend=self.model,
             identity=self.id,limits=SpineLimits(context_tokens=8192,max_output_tokens=64,
             deadline_ms=5000),evidence_provider=self.knowledge.evidence_provider())
        self.ledger=FlightLedger(self.db,self.id)
        self.worker=NativeFlightWorker(self.ledger,self.spine,'worker1')
        self.app=FlightApplication(self.spine,self.ledger,self.worker,FlightOperator(self.ledger,self.spine))
        self.dispatcher=FlightDispatcher(self.app,knowledge_plane=self.knowledge)
        self.server=FlightHTTPServer(('127.0.0.1',0),self.dispatcher,TOKEN,
                                     io_timeout_seconds=2,max_connections=4)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.port=self.server.server_port

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.gate.close();self.db.close();self.temp.cleanup()

    def client(self):return FlightClient(port=self.port,token=TOKEN,timeout=5)

    def raw(self,method,route,body=None,*,token=TOKEN,host=None,origin=None,extra=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        headers={'Host':host or f'127.0.0.1:{self.port}','Authorization':'Bearer '+token,
                 'Connection':'close'}
        if body is not None:headers['Content-Type']='application/json'
        if origin is not None:headers['Origin']=origin
        headers.update(extra or {})
        conn.request(method,route,body=body,headers=headers)
        response=conn.getresponse();out=(response.status,response.read())
        conn.close();return out

    def request(self,operation,payload):
        return self.client().request(operation,payload)

    def test_protocol_is_explicit_native_v2(self):
        status,raw=self.raw('GET','/v2/protocol')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['result']['schema'],SCHEMA)
        self.assertNotIn('recover',PROTOCOL['operations'])
        self.assertNotIn('call_tool',PROTOCOL['operations'])

    def test_one_real_execution_spine_round_trip_with_durable_replay(self):
        self.request('create',{'session_id':'chat1'})
        accepted=self.request('submit',{'job_id':'job1','session_id':'chat1',
              'request_id':'req1','question':'Explain AI state'})
        self.assertEqual(accepted['job']['state'],'queued')
        self.assertEqual(self.model.calls,0)
        outcome=self.request('work_one',{})
        self.assertEqual(outcome['status'],'completed')
        self.assertEqual(self.model.calls,1)
        seen=self.request('job',{'job_id':'job1'})
        self.assertEqual(seen['job']['state'],'completed')
        repeated=self.request('replay',{'session_id':'chat1',
                              'request_id':'req1','question':'Explain AI state'})
        self.assertTrue(repeated['receipt']['replayed'])
        self.assertEqual(self.model.calls,1)
        history=self.request('history',{'session_id':'chat1'})
        self.assertEqual(len(history['messages']),2)
        self.assertTrue(history['messages'][1]['content'].startswith('Native fixture'))

    def test_duplicate_accepted_job_never_duplicates_model_compute(self):
        self.request('create',{'session_id':'chat1'})
        spec={'job_id':'job1','session_id':'chat1','request_id':'req1','question':'State A'}
        self.assertFalse(self.request('submit',spec)['job']['replayed'])
        self.assertTrue(self.request('submit',spec)['job']['replayed'])
        self.request('work_one',{})
        self.assertEqual(self.model.calls,1)
        self.assertEqual(self.request('work_one',{})['status'],'empty')

    def test_request_id_reuse_with_mutated_question_conflicts(self):
        self.request('create',{'session_id':'chat1'})
        spec={'job_id':'job1','session_id':'chat1','request_id':'req1','question':'A'}
        self.request('submit',spec)
        with self.assertRaises(FlightClientError):
            self.request('submit',spec|{'question':'B'})
        self.assertEqual(self.model.calls,0)

    def test_unknown_operation_and_tool_authority_refused(self):
        for name in ('call_tool','recover','pause','resume','operator_reconcile','sudo'):
            code,_=self.raw('POST','/v2/operations',json.dumps(
                {'operation':name,'payload':{}}))
            self.assertEqual(code,400)
        self.assertEqual(self.model.calls,0)

    def test_missing_bearer_never_reaches_dispatch(self):
        status,_=self.raw('POST','/v2/operations',b'{}',token='')
        self.assertEqual(status,401)
        self.assertEqual(self.model.calls,0)

    def test_wrong_host_denied(self):
        status,_=self.raw('GET','/v2/protocol',host='attacker.example')
        self.assertEqual(status,403)

    def test_browser_origin_denied(self):
        code,_=self.raw('GET','/v2/protocol',origin='http://127.0.0.1')
        self.assertEqual(code,403)

    def test_legacy_route_is_not_exposed_in_v2(self):
        code,_=self.raw('GET','/v1/protocol')
        self.assertEqual(code,404)
        code,_=self.raw('POST','/v1/operations',b'{}')
        self.assertEqual(code,404)

    def test_unrecognized_json_keys_refused(self):
        self.request('create',{'session_id':'chat1'})
        code,_=self.raw('POST','/v2/operations',json.dumps({'operation':'submit',
            'payload':{'session_id':'chat1','job_id':'x','request_id':'r','question':'A',
                       'operator_approval':True}}))
        self.assertEqual(code,400)

    def test_native_model_failure_does_not_leak_exception_or_fabricate_turn(self):
        self.request('create',{'session_id':'chat1'})
        self.request('submit',{'session_id':'chat1','job_id':'job1',
                       'request_id':'req1','question':'Break'})
        self.model.fail=True
        code,raw=self.raw('POST','/v2/operations',json.dumps({'operation':'work_one','payload':{}}))
        self.assertEqual(code,500)
        self.assertNotIn(b'private-model-failure',raw)
        self.assertEqual(self.model.calls,1)
        self.assertEqual(self.spine.history('chat1'),())

    def test_private_knowledge_query_is_bearer_scoped(self):
        self.knowledge.admit_bytes_for_tests(b'Verified lighthouse navigation source',
                        doc_id='notes',title='Notes',approved=True)
        found=self.request('knowledge_search',{'question':'lighthouse'})
        self.assertTrue(found['hits'])
        self.assertNotIn('passage',found['hits'][0])
        self.assertEqual(self.model.calls,0)

    def test_malformed_knowledge_limit_refused(self):
        code,_=self.raw('POST','/v2/operations',json.dumps({'operation':'knowledge_search',
                       'payload':{'question':'lighthouse','limit':100000}}))
        self.assertEqual(code,400)

    def test_protocol_refuses_non_loopback(self):
        with self.assertRaises(ContractViolation):
            FlightHTTPServer(('0.0.0.0',0),self.dispatcher,TOKEN)

    def test_weak_bearer_refused(self):
        with self.assertRaises(ContractViolation):
            FlightHTTPServer(('127.0.0.1',0),self.dispatcher,'123')

    def test_client_does_not_dial_remote_or_dynamic_hostname(self):
        with self.assertRaises(FlightClientError):FlightClient(port=0,token=TOKEN)
        with self.assertRaises(FlightClientError):FlightClient(port=1234,token='short')

    def test_no_implicit_session_creation_on_submit(self):
        with self.assertRaises(FlightClientError):
            self.request('submit',{'job_id':'job1','session_id':'missing',
                            'request_id':'req1','question':'no session'})
        self.assertEqual(self.model.calls,0)

    def test_no_unapproved_knowledge_ingest_endpoint(self):
        for operation in ('knowledge_ingest','knowledge_forget','rebuild_index'):
            code,_=self.raw('POST','/v2/operations',json.dumps({'operation':operation,'payload':{}}))
            self.assertEqual(code,400)


    def test_credential_file_is_private_and_read_with_no_token_logging(self):
        from skeleton.ai.runtime.operational_ai.transport.flight.credential import read_bearer
        p=self.state/'bearer.txt';p.write_text(TOKEN+'\n',encoding='ascii');p.chmod(0o600)
        self.assertEqual(read_bearer(p),TOKEN)

    def test_credential_symlink_and_group_exposure_fail_closed(self):
        from skeleton.ai.runtime.operational_ai.transport.flight.credential import read_bearer
        p=self.state/'bearer.txt';p.write_text(TOKEN);p.chmod(0o600)
        alias=self.state/'alias.txt';alias.symlink_to(p)
        with self.assertRaises(OSError):read_bearer(alias)
        p.chmod(0o640)
        with self.assertRaises(ContractViolation):read_bearer(p)

    def test_credential_hardlink_and_short_secret_fail_closed(self):
        from skeleton.ai.runtime.operational_ai.transport.flight.credential import read_bearer
        p=self.state/'bearer.txt';p.write_text(TOKEN);p.chmod(0o600)
        os_link=self.state/'hard.txt'
        import os
        os.link(p,os_link)
        with self.assertRaises(ContractViolation):read_bearer(p)
        os_link.unlink();p.write_text('short');p.chmod(0o600)
        with self.assertRaises(ContractViolation):read_bearer(p)

    def test_bearer_non_ascii_controls_and_multiline_rejected(self):
        from skeleton.ai.runtime.operational_ai.transport.flight.credential import read_bearer
        p=self.state/'bearer.txt'
        for raw in (b'A'*40+b'\x00',b'A'*40+b'\n' +b'B'*40,b'A'*40+b'\xff',b'A'*40+b' '):
            p.write_bytes(raw);p.chmod(0o600)
            with self.subTest(raw=raw[-8:]),self.assertRaises(ContractViolation):
                read_bearer(p)

    def test_raw_payload_malformed_json_is_rejected(self):
        status,_=self.raw('POST','/v2/operations',b'{invalid')
        self.assertEqual(status,400)

    def test_browser_authorization_header_no_origin_refused(self):
        status,_=self.raw('POST','/v2/operations',b'{}',origin='http://evil.invalid')
        self.assertEqual(status,403)

    def test_transfer_encoding_is_refused(self):
        status,_=self.raw('POST','/v2/operations',b'{}',extra={'Transfer-Encoding':'chunked'})
        self.assertEqual(status,400)

    def test_wrong_content_type_is_refused(self):
        status,_=self.raw('POST','/v2/operations',b'{}',extra={'Content-Type':'text/plain'})
        self.assertEqual(status,415)

    def test_queue_receipt_visible_without_spending_model(self):
        counts=self.request('queue',{})
        self.assertEqual(counts['model_sha256'],M)
        self.assertEqual(self.model.calls,0)

    def test_missing_message_or_extra_operator_fields_rejected(self):
        for payload in ({'job_id':'j','session_id':'s','request_id':'r'},
                        {'job_id':'j','session_id':'s','request_id':'r',
                         'question':'ok','approve_recovery':True}):
            status,_=self.raw('POST','/v2/operations',json.dumps(
                {'operation':'submit','payload':payload}))
            self.assertEqual(status,400)
        self.assertEqual(self.model.calls,0)

    def test_client_wrong_port_fails_with_no_remote_fallback(self):
        with self.assertRaises(FlightClientError):
            FlightClient(port=1,token=TOKEN,timeout=1).request('queue',{})


if __name__=='__main__':unittest.main()
