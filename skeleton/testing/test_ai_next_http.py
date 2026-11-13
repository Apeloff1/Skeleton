"""Actual loopback socket protocol tests; no model/mock backend is claimed."""
from __future__ import annotations

import http.client
import json
import threading
import unittest

from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
from skeleton.ai.runtime.operational_ai.transport.http import LocalHTTPServer

TOKEN = 't'*64


class EchoDispatcher:
    def __init__(self):
        self.calls = []

    def dispatch(self, operation, payload):
        self.calls.append((operation, payload))
        return {'operation':operation, 'accepted':True}


class TestLocalHTTP(unittest.TestCase):
    def setUp(self):
        self.dispatcher = EchoDispatcher()
        self.server = LocalHTTPServer(('127.0.0.1', 0), self.dispatcher, TOKEN,
                                      io_timeout_seconds=1)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.05},daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method='GET', path='/v1/protocol', *, headers=None, data=None):
        h={'Authorization':'Bearer '+TOKEN}
        h.update(headers or {})
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            client.request(method,path,body=data,headers=h)
            result=client.getresponse()
            raw=result.read()
            try:
                body=json.loads(raw) if raw else None
            except json.JSONDecodeError:
                body=raw.decode('utf-8',errors='replace')
            return result.status, body
        finally:client.close()

    def test_authenticated_protocol(self):
        status,response=self.request()
        self.assertEqual(status,200)
        self.assertEqual(response['status'],'ok')

    def test_missing_token_rejected(self):
        status,_=self.request(headers={'Authorization':''})
        self.assertEqual(status,401)

    def test_wrong_token_rejected(self):
        status,_=self.request(headers={'Authorization':'Bearer '+('x'*64)})
        self.assertEqual(status,401)

    def test_origin_denied_even_with_valid_token(self):
        status,_=self.request(headers={'Origin':'http://localhost'})
        self.assertEqual(status,403)

    def test_host_confusion_denied(self):
        status,_=self.request(headers={'Host':'evil.example'})
        self.assertEqual(status,403)

    def test_transfer_encoding_denied(self):
        status,_=self.request(headers={'Transfer-Encoding':'chunked'})
        self.assertEqual(status,400)

    def test_expect_continue_refused(self):
        status,_=self.request('POST','/v1/operations',headers={
            'Expect':'100-continue','Content-Type':'application/json'},data=b'{}')
        self.assertEqual(status,417)

    def test_unknown_path_denied(self):
        status,_=self.request(path='/v1/protocol?token=1')
        self.assertEqual(status,404)

    def test_post_contract_roundtrip(self):
        payload=json.dumps({'operation':'ping','payload':{'value':3}}).encode()
        status,response=self.request('POST','/v1/operations',headers={
            'Content-Type':'application/json'},data=payload)
        self.assertEqual(status,200)
        self.assertEqual(self.dispatcher.calls,[('ping',{'value':3})])
        self.assertEqual(response['result']['accepted'],True)

    def test_invalid_json_rejected(self):
        status,_=self.request('POST','/v1/operations',headers={
            'Content-Type':'application/json'},data=b'{bad')
        self.assertEqual(status,400)

    def test_content_type_required(self):
        status,_=self.request('POST','/v1/operations',headers={
            'Content-Type':'text/plain'},data=b'abc')
        self.assertEqual(status,415)

    def test_oversized_body_denied_before_read(self):
        status,_=self.request('POST','/v1/operations',headers={
            'Content-Type':'application/json', 'Content-Length':'100000000'},data=b'{}')
        self.assertEqual(status,413)

    def test_duplicate_host_rejected(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            conn.putrequest('GET','/v1/protocol',skip_host=True)
            conn.putheader('Host',f'127.0.0.1:{self.server.server_port}')
            conn.putheader('Host',f'127.0.0.1:{self.server.server_port}')
            conn.putheader('Authorization','Bearer '+TOKEN)
            conn.endheaders()
            response=conn.getresponse()
            self.assertEqual(response.status,400)
            response.read()
        finally:conn.close()

    def test_duplicate_authorization_rejected(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            conn.putrequest('GET','/v1/protocol')
            conn.putheader('Authorization','Bearer '+TOKEN)
            conn.putheader('Authorization','Bearer '+TOKEN)
            conn.endheaders()
            response=conn.getresponse()
            self.assertEqual(response.status,400)
            response.read()
        finally:conn.close()

    def test_slot_refuses_overadmission(self):
        self.assertTrue(self.server._slots.acquire(blocking=False))
        try:
            # The server has seven remaining slots; this verifies bounded
            # accounting without depending on network scheduling.
            owned=[self.server._slots.acquire(blocking=False) for _ in range(7)]
            self.assertEqual(owned,[True]*7)
            self.assertFalse(self.server._slots.acquire(blocking=False))
            for _ in range(7):self.server._slots.release()
        finally:self.server._slots.release()

    def test_reject_nonloopback_binding(self):
        with self.assertRaises(ContractViolation):
            LocalHTTPServer(('0.0.0.0',0),self.dispatcher,TOKEN)

    def test_reject_weak_token(self):
        with self.assertRaises(ContractViolation):
            LocalHTTPServer(('127.0.0.1',0),self.dispatcher,'tiny')

    def test_reject_invalid_limits(self):
        for value in (0,65,True):
            with self.subTest(value=value), self.assertRaises(ContractViolation):
                LocalHTTPServer(('127.0.0.1',0),self.dispatcher,TOKEN,max_connections=value)


if __name__=='__main__':
    unittest.main()
