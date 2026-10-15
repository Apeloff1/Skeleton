"""Loopback and same-origin security contracts, no real emulator workers."""
from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from skeleton.jeeves.game_comparison_live_http import LocalComparisonServer


class FakeStudy:
    def __init__(self):
        self.steps=0
        self.closed=False
    def state(self):
        return {"schema_version":"synthetic-test-view","lanes":{}}
    def step(self,packet):
        self.steps+=1
        return {"status":"fake-test-only","accepted":packet}
    def reset(self,game_id):
        return {"status":"synthetic-reset","game_id":game_id}
    def checkpoint(self,game_id):
        return {"status":"synthetic-private-checkpoint","game_id":game_id}
    def rewind(self,game_id):
        return {"status":"synthetic-private-rewind","game_id":game_id}
    def export_evidence(self):
        return {"schema_version":"synthetic-no-native-evidence"}
    def close(self):
        self.closed=True


class LocalOriginContracts(unittest.TestCase):
    def setUp(self):
        self.study=FakeStudy()
        self.server=LocalComparisonServer(self.study,0,60)
        self.base="http://127.0.0.1:"+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.stop()
        self.server.server_close()
        self.thread.join(timeout=3)

    def _call(self,path,*,method="GET",body=None,token=None,origin=None):
        headers={}
        if token is not None:headers["X-Study-Token"]=token
        if origin is not None:headers["Origin"]=origin
        if body is not None:headers["Content-Type"]="application/json"
        request=urllib.request.Request(
            self.base+path,data=json.dumps(body).encode() if body is not None else None,
            headers=headers,method=method,
        )
        try:
            with urllib.request.urlopen(request,timeout=3) as response:
                return response.status,json.loads(response.read()) if path!="/" else response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code,json.loads(error.read())

    def test_get_state_requires_random_token(self):
        status,_=self._call("/api/state")
        self.assertEqual(status,403)
        status,_=self._call("/api/state",token=self.server.secret)
        self.assertEqual(status,200)

    def test_post_rejects_cross_origin_even_with_token(self):
        status,_=self._call(
            "/api/step",method="POST",body={"steps":[]},
            token=self.server.secret,origin="https://example.org",
        )
        self.assertEqual(status,403)
        self.assertEqual(self.study.steps,0)
        status,_=self._call(
            "/api/step",method="POST",body={"steps":[]},
            token=self.server.secret,origin=self.base,
        )
        self.assertEqual(status,200)
        self.assertEqual(self.study.steps,1)

    def test_checkpoint_and_rewind_are_authenticated_same_origin_only(self):
        for endpoint in ("/api/checkpoint","/api/rewind"):
            status,_=self._call(
                endpoint,method="POST",body={"game_id":"first"},
                token=self.server.secret,origin="https://untrusted.invalid",
            )
            self.assertEqual(status,403)
            status,receipt=self._call(
                endpoint,method="POST",body={"game_id":"first"},
                token=self.server.secret,origin=self.base,
            )
            self.assertEqual(status,200)
            self.assertEqual(receipt["game_id"],"first")
            self.assertEqual(set(receipt),{"status","game_id"})
            status,_=self._call(
                endpoint,method="POST",body={"game_id":"first","path":"/etc"},
                token=self.server.secret,origin=self.base,
            )
            self.assertEqual(status,400)

    def test_home_page_restrictive_security_policy(self):
        request=urllib.request.Request(self.base+"/")
        with urllib.request.urlopen(request,timeout=3) as response:
            html=response.read().decode()
            csp=response.headers["Content-Security-Policy"]
        self.assertIn("connect-src 'self'",csp)
        self.assertIn("frame-ancestors 'none'",csp)
        self.assertIn('nonce="'+self.server.nonce+'"',html)
        self.assertIn("root.append(deckFor(id));",html)


if __name__=="__main__":
    unittest.main()
