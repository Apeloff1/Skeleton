"""Real socket/framing/authorization integration with contract-only test double."""
import http.client
import json
import threading
import unittest
from skeleton.testing.laptop_runtime_test_support import FakeWorker
from skeleton.ai.runtime.operational_ai.laptop_runtime.dispatcher import LaptopDispatcher
from skeleton.ai.runtime.operational_ai.laptop_runtime.server import LaptopHTTPServer
from skeleton.ai.runtime.operational_ai.laptop_runtime.client import LaptopClient
class TestLoopbackHTTP(unittest.TestCase):
    def setUp(self):
        self.secret="X"*64
        self.worker=FakeWorker()
        self.server=LaptopHTTPServer(("127.0.0.1",0),
            LaptopDispatcher(self.worker),self.secret,max_connections=2)
        self.thread=threading.Thread(target=self.server.serve_forever,
                                     kwargs={"poll_interval":0.05},daemon=True)
        self.thread.start()
        self.port=self.server.server_port
    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
    def _raw(self,method,path,body=b"",headers=None):
        client=http.client.HTTPConnection("127.0.0.1",self.port,timeout=3)
        client.request(method,path,body=body,headers=headers or {})
        response=client.getresponse()
        result=(response.status,response.read())
        client.close()
        return result
    def test_real_loopback_create_turn_replay(self):
        client=LaptopClient(port=self.port,bearer=self.secret)
        sid=client.create()["session_id"]
        first=client.turn(sid,"r1","hello")
        self.assertEqual(first["receipt"]["text"],"hello")
        self.assertEqual(self.worker.generation_calls,1)
        replay=client.replay(sid,"r1","hello")
        self.assertTrue(replay["found"])
        self.assertEqual(self.worker.generation_calls,1)
    def test_bearer_is_required_for_every_request(self):
        status,_=self._raw("GET","/v1/protocol")
        self.assertEqual(status,401)
        status,_=self._raw("POST","/v1/operations",b"{}",
            {"Content-Type":"application/json"})
        self.assertEqual(status,401)
    def test_authorized_protocol_is_real_interface(self):
        status,body=self._raw("GET","/v1/protocol",headers={
            "Authorization":"Bearer "+self.secret})
        self.assertEqual(status,200)
        payload=json.loads(body)
        self.assertEqual(payload["result"]["schema"],
                         "skeleton.operational-ai.laptop-api.v1")
    def test_browser_origin_cannot_reach_local_model(self):
        status,_=self._raw("GET","/v1/protocol",headers={
            "Authorization":"Bearer "+self.secret,
            "Origin":"https://untrusted.example"})
        self.assertEqual(status,403)
    def test_unknown_route_refused_after_auth(self):
        status,_=self._raw("GET","/v1/unapproved",headers={
            "Authorization":"Bearer "+self.secret})
        self.assertEqual(status,404)
if __name__=="__main__":unittest.main()
