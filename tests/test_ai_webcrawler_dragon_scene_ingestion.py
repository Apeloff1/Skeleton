"""Canonical CrawlRun capture, hashing and replay of game/vector source data."""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.core import FetchResponse,CrawlPolicy
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun
from tests.test_ai_webcrawler_dragon_vector_mesh import SVG,PLY,OFF
from tests.test_ai_webcrawler_dragon_game_scenes import GODOT,UNITY,USDA,LDRAW


class SceneFetcher:
    timeout_seconds=4
    transport_mode="scripted_game_scene_inventory"
    def __init__(self,mime,payload):
        self.mime,self.payload,self.calls=mime,payload.encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/asset":
            raise AssertionError("scene resource reference generated network IO")
        if len(self.payload)>max_bytes:
            raise AssertionError("scripted scene exceeded reserved response bytes")
        return FetchResponse(url,200,{"content-type":self.mime},
                             self.payload,time.time())


class CanonicalSceneTests(unittest.TestCase):
    def capture(self,mime,payload):
        at=time.time()
        fetcher=SceneFetcher(mime,payload)
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/asset",),
                allowed_hosts=("example.com",),max_depth=1,max_requests=4,
                max_documents=2,max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"scene-evidence-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,"expires_at":at+3600},
            now=at,fetcher=fetcher,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=at+offset):
                run.run_slice(
                    max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,
                    on_checkpoint=lambda snapshot,event:None,
                )
        return run,fetcher

    def test_seven_asset_families_through_actual_canonical_worker(self):
        samples=(
            ("image/svg+xml",SVG,"Vector primitive path: 1"),
            ("model/ply",PLY,"Vertices: 3; polygon faces: 1"),
            ("model/off",OFF,"Vertices: 3; faces: 1"),
            ("application/x-godot-scene",GODOT,"Node3D=1"),
            ("application/x-unity-scene",UNITY,"GameObject=1"),
            ("model/vnd.usda",USDA,"Xform=1"),
            ("text/x-ldraw",LDRAW,"triangle primitives: 1"),
        )
        for mime,source,expected in samples:
            with self.subTest(mime=mime):
                run,fetcher=self.capture(mime,source)
                state=run.snapshot()
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(state["frontier"],[])
                self.assertEqual(len(fetcher.calls),2)
                item=run.sources()[0]
                self.assertIn(expected,item["text"])
                self.assertEqual(item["review_state"],"unreviewed")
                self.assertFalse(item["provenance"]["training_permission"])
                self.assertFalse(item["provenance"]["raw_bytes_retained"])
                self.assertEqual(
                    CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state,
                )

    def test_malformed_xml_consumes_attempt_without_source(self):
        run,fetcher=self.capture("image/svg+xml","<svg><script>alert(1)</script></svg>")
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)

    def test_externally_named_scene_assets_do_not_trigger_requests(self):
        run,fetcher=self.capture("application/x-godot-scene",GODOT)
        self.assertEqual(state:=run.snapshot(),CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot())
        self.assertEqual(len(fetcher.calls),2)

    def test_mime_types_explicit_only(self):
        allowed=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("image/svg+xml","model/ply","model/off",
                     "application/x-godot-scene","application/x-unity-scene",
                     "model/vnd.usda","text/x-ldraw"):
            self.assertIn(mime,allowed)


if __name__=="__main__":
    unittest.main()
