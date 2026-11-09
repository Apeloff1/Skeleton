"""Real canonical acquisition, accounting and replay for extended binary media."""
from __future__ import annotations

import io
import json
import struct
import tarfile
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse, CrawlPolicy
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun
from tests.test_ai_webcrawler_dragon_webp import vp8x
from tests.test_ai_webcrawler_dragon_flac import flac
from tests.test_ai_webcrawler_dragon_ogg import opus
from tests.test_ai_webcrawler_dragon_mp4 import movie
from tests.test_ai_webcrawler_dragon_glb import glb
from tests.test_ai_webcrawler_dragon_stl import stl
from tests.test_ai_webcrawler_dragon_ico import ico
from tests.test_ai_webcrawler_dragon_tar import tar


class Transport:
    timeout_seconds=4
    transport_mode="scripted_extended_binary_media"
    def __init__(self,mime,body):
        self.mime,self.body,self.calls=mime,body,[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(
                url,200,{"content-type":"text/plain"},
                b"User-agent: *\nAllow: /\n",time.time(),
            )
        if url!="https://example.com/artifact":
            raise AssertionError("binary metadata initiated unapproved acquisition")
        if len(self.body)>max_bytes:
            raise AssertionError("scripted transport exceeded request byte cap")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())


class CanonicalExtendedMedia(unittest.TestCase):
    def run_source(self,mime,blob):
        at=time.time()
        transport=Transport(mime,blob)
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/artifact",),
                allowed_hosts=("example.com",),
                max_depth=1,max_requests=4,max_documents=2,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"extended-binary-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,
                     "expires_at":at+3600},
            now=at,fetcher=transport,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=at+offset):
                run.run_slice(max_steps=1,max_seconds=1,
                              authorize=lambda:None,cancelled=lambda:False,
                              on_checkpoint=lambda snap,event:None)
        return run,transport

    def test_all_extended_binary_formats_use_one_canonical_worker(self):
        cases=(
            ("image/webp",vp8x(),"64 x 128"),
            ("audio/flac",flac(),"44100"),
            ("audio/ogg",opus(),"Opus-in-Ogg"),
            ("video/mp4",movie(),"2.300"),
            ("model/gltf-binary",glb(),"Nodes: 1"),
            ("model/stl",stl(),"Triangles: 1"),
            ("image/x-icon",ico(),"32 x 32"),
            ("application/x-tar",tar(),"Extension class .obj"),
        )
        for mime,data,expected in cases:
            with self.subTest(mime=mime):
                run,fetcher=self.run_source(mime,data)
                state=run.snapshot()
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(state["frontier"],[])
                self.assertEqual(len(fetcher.calls),2)
                self.assertIn(expected,run.sources()[0]["text"])
                self.assertEqual(run.sources()[0]["review_state"],"unreviewed")
                self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
                self.assertFalse(run.sources()[0]["provenance"]["raw_bytes_retained"])
                self.assertEqual(
                    CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),
                    state,
                )

    def test_corrupt_mp4_consumes_request_without_source(self):
        run,fetcher=self.run_source("video/mp4",movie()[:-1])
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)

    def test_external_source_url_never_generated_from_asset_content(self):
        run,fetcher=self.run_source("model/gltf-binary",glb())
        self.assertEqual(run.snapshot()["frontier"],[])
        self.assertEqual(len(fetcher.calls),2)

    def test_explicit_mime_admission_no_generic_video_execution(self):
        types=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("image/webp","audio/flac","audio/ogg","video/mp4",
                     "model/gltf-binary","model/stl","image/x-icon",
                     "application/x-tar"):
            self.assertIn(mime,types)
        self.assertNotIn("application/x-msdownload",types)


if __name__=="__main__":
    unittest.main()
